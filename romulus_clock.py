romulus_clock.py

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import aiohttp
import threading
from flask import Flask, jsonify
from dataclasses import dataclass, asdict
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
SENTI_LOG = logging.getLogger('RomulusClock')

@dataclass
class ClockState:
    market_time: Optional[datetime] = None
    source: str = "system"
    last_updated: Optional[datetime] = None
    error_count: int = 0
    is_healthy: bool = True

class RomulusClock:
    def __init__(self, pair_list: List[Tuple[str, str]], poll_interval: int = 10):
        self.pair_list = pair_list
        self.poll_interval = poll_interval
        self.state = ClockState()
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self.max_retries = 3
        self.request_timeout = 5
        self.max_error_count = 5
        
    async def _create_session(self):
        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def _close_session(self):
        if self.session:
            await self.session.close()
    
    async def _fetch_dexscreener_time(self, chain_id: str, pair_address: str) -> Optional[datetime]:
        if not self.session:
            await self._create_session()
            
        url = f"https://api.dexscreener.com/latest/dex/pairs/{chain_id}/{pair_address}"
        
        for attempt in range(self.max_retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pair_info = data.get('pair', {})
                        timestamp_ms = pair_info.get('pairCreatedAt')
                        
                        if timestamp_ms:
                            market_time = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
                            SENTI_LOG.info(f"Successfully fetched time from Dexscreener: {market_time}")
                            return market_time
                        else:
                            SENTI_LOG.warning(f"No pairCreatedAt found in response for {chain_id}/{pair_address}")
                    else:
                        SENTI_LOG.warning(f"Dexscreener API returned status {response.status}")
                        
            except asyncio.TimeoutError:
                SENTI_LOG.warning(f"Timeout fetching from Dexscreener (attempt {attempt + 1}/{self.max_retries})")
            except Exception as e:
                SENTI_LOG.error(f"Error fetching from Dexscreener (attempt {attempt + 1}/{self.max_retries}): {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)
        
        return None
    
    def _get_fallback_time(self) -> datetime:
        return datetime.now(timezone.utc)
    
    async def _update_clock(self):
        market_time = None
        source = "system"
        
        for chain_id, pair_address in self.pair_list:
            market_time = await self._fetch_dexscreener_time(chain_id, pair_address)
            if market_time:
                source = "Dexscreener"
                break
        
        if not market_time:
            market_time = self._get_fallback_time()
            self.state.error_count += 1
            SENTI_LOG.warning(f"Using fallback system time. Error count: {self.state.error_count}")
        else:
            self.state.error_count = 0
        
        self.state.market_time = market_time
        self.state.source = source
        self.state.last_updated = datetime.now(timezone.utc)
        self.state.is_healthy = self.state.error_count < self.max_error_count
        
        SENTI_LOG.info(f"[RomulusClock] Updated - Time: {market_time}, Source: {source}, Healthy: {self.state.is_healthy}")
    
    async def _polling_loop(self):
        SENTI_LOG.info("RomulusClock polling loop started")
        
        while self.running:
            try:
                await self._update_clock()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                SENTI_LOG.error(f"Error in polling loop: {e}")
                await asyncio.sleep(self.poll_interval)
        
        SENTI_LOG.info("RomulusClock polling loop stopped")
    
    async def start(self):
        if self.running:
            SENTI_LOG.warning("RomulusClock is already running")
            return
        
        self.running = True
        await self._create_session()
        await self._update_clock()
        asyncio.create_task(self._polling_loop())
        SENTI_LOG.info("RomulusClock started successfully")
    
    async def stop(self):
        self.running = False
        await self._close_session()
        SENTI_LOG.info("RomulusClock stopped")
    
    def get_clock_data(self) -> Dict:
        if not self.state.market_time or not self.state.last_updated:
            return {
                "error": "Clock not initialized",
                "marketTime": None,
                "source": None,
                "lastUpdated": None,
                "isHealthy": False
            }
        
        return {
            "marketTime": self.state.market_time.isoformat(),
            "source": self.state.source,
            "lastUpdated": self.state.last_updated.isoformat(),
            "isHealthy": self.state.is_healthy,
            "errorCount": self.state.error_count
        }
    
    def is_stale(self, threshold_seconds: int = None) -> bool:
        if threshold_seconds is None:
            threshold_seconds = self.poll_interval * 2
        
        if not self.state.last_updated:
            return True
        
        time_since_update = datetime.now(timezone.utc) - self.state.last_updated
        return time_since_update.total_seconds() > threshold_seconds

# Flask app
app = Flask(__name__)
ROMULUS_CLOCK: Optional[RomulusClock] = None

@app.route('/romulus-clock', methods=['GET'])
def get_romulus_clock():
    if not ROMULUS_CLOCK:
        return jsonify({"error": "RomulusClock not initialized"}), 500
    
    clock_data = ROMULUS_CLOCK.get_clock_data()
    if ROMULUS_CLOCK.is_stale():
        clock_data["warning"] = "Clock data may be stale"
    
    return jsonify(clock_data)

@app.route('/romulus-clock/health', methods=['GET'])
def get_clock_health():
    if not ROMULUS_CLOCK:
        return jsonify({"healthy": False, "error": "Clock not initialized"}), 500
    
    is_healthy = ROMULUS_CLOCK.state.is_healthy and not ROMULUS_CLOCK.is_stale()
    
    return jsonify({
        "healthy": is_healthy,
        "isStale": ROMULUS_CLOCK.is_stale(),
        "errorCount": ROMULUS_CLOCK.state.error_count,
        "lastUpdated": ROMULUS_CLOCK.state.last_updated.isoformat() if ROMULUS_CLOCK.state.last_updated else None
    })

async def init_romulus_clock():
    global ROMULUS_CLOCK
    
    PAIR_LIST = [
        ("ethereum", "0x6982508145454Ce325dDbE47a25d4ec3d2311933"),  # PEPE/WETH
        ("ethereum", "0x8ad599c3a0ff1de082011efddc58f1908eb6e6d8"),  # ETH/USDC (Uniswap V3)
    ]
    
    ROMULUS_CLOCK = RomulusClock(
        pair_list=PAIR_LIST,
        poll_interval=10
    )
    
    await ROMULUS_CLOCK.start()

def run_flask_app():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

async def main():
    await init_romulus_clock()
    
    flask_thread = threading.Thread(target=run_flask_app, daemon=True)
    flask_thread.start()
    
    SENTI_LOG.info("RomulusClock system fully initialized")
    SENTI_LOG.info("REST API available at: http://localhost:5000/romulus-clock")
    SENTI_LOG.info("Health check available at: http://localhost:5000/romulus-clock/health")
    
    try:
        while True:
            await asyncio.sleep(60)
            if ROMULUS_CLOCK and ROMULUS_CLOCK.is_stale():
                SENTI_LOG.warning("⚠️  RomulusClock data is stale!")
    except KeyboardInterrupt:
        SENTI_LOG.info("Shutting down RomulusClock...")
        if ROMULUS_CLOCK:
            await ROMULUS_CLOCK.stop()

if __name__ == "__main__":
    asyncio.run(main())

