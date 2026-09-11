import asyncio
import os
import random
from fastapi import HTTPException
from common.runtime import create_app

app = create_app()
DELAY = float(os.getenv("RESPONSE_DELAY_MS", "50")) / 1000
FAILURE_RATE = float(os.getenv("FAILURE_RATE", "0"))
if DELAY < 0 or not 0 <= FAILURE_RATE <= 1:
    raise ValueError("Invalid simulator configuration")


@app.get("/fuente")
async def source():
    await asyncio.sleep(DELAY)
    if random.random() < FAILURE_RATE:
        raise HTTPException(503, "Simulated dependency failure")
    return {"source": "synthetic", "value": "ok", "configured_delay_ms": DELAY * 1000}


@app.get("/health")
async def health():
    return {"status": "ok"}
