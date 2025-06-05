# main.py
from fastapi import FastAPI
from datetime import datetime
import pytz

app = FastAPI(
    title="Romulus Clock",
    description="Accurate UK Time API for Romulus & Kai agents",
    version="1.0.0"
)

@app.get("/time")
def get_time():
    uk_tz = pytz.timezone("Europe/London")
    now = datetime.now(uk_tz)
    return {
        "time": now.strftime("%H:%M"),
        "timestamp_iso": now.isoformat(),
        "timezone": "Europe/London",
        "utc_offset": now.strftime("%z"),
        "is_dst": bool(now.dst())
    }

@app.get("/health")
def health():
    return { "status": "healthy" }
