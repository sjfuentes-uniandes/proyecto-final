import os
from fastapi import HTTPException, Request
from common.runtime import create_app, fetch_one

app = create_app(database=True)
VERSION = os.getenv("RULES_VERSION", "synthetic-v1")


@app.get("/catalogo")
async def catalog(request: Request):
    row = await fetch_one(request, "SELECT payload FROM experiment_catalog WHERE version = %s", (VERSION,))
    if row is None:
        raise HTTPException(503, "Synthetic dataset not loaded")
    return row["payload"]


@app.get("/health")
async def health(request: Request):
    await catalog(request)
    return {"status": "ok"}
