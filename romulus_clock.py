# romulus_clock.py
from fastapi import FastAPI, HTTPException
from datetime import datetime
from zoneinfo import ZoneInfo
import uvicorn

app = FastAPI()

@app.get("/time")
def get_time(timezone: str = "UTC"):
    """Return the current time in the specified timezone.

    The timezone parameter should be a valid IANA timezone string, e.g.
    ``"Europe/London"`` for UK time. Defaults to ``"UTC"``.
    """
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timezone")

    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    return {"timezone": timezone, "time": now}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
