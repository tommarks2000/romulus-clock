# romulus_clock.py
from fastapi import FastAPI
from datetime import datetime
import uvicorn

app = FastAPI()

@app.get("/time")
def get_time():
    utc_now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    return {"utc_time": utc_now}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
