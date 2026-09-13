import asyncio
import os
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb
from common.runtime import DATASET, HEADER, create_app, fetch_one, measure

app = create_app(database=True)
CATALOG = os.environ["CATALOG_URL"].rstrip("/")
SOURCE = os.environ["EXTERNAL_SOURCE_URL"].rstrip("/")
TIMEOUT = float(os.getenv("EXTERNAL_SOURCE_TIMEOUT_MS", "150")) / 1000
CACHE_ENABLED = os.getenv("RULES_CACHE_ENABLED", "true").lower() == "true"
if TIMEOUT <= 0 or int(os.getenv("EXTERNAL_SOURCE_RETRIES", "0")) != 0:
    raise ValueError("Use a positive timeout and zero retries for this experiment")
cache_lock = asyncio.Lock()
cached_catalog = None


class QuoteInput(BaseModel):
    product_id: str = Field(default="producto-sintetico", min_length=1, max_length=64)


async def catalog(request):
    global cached_catalog
    if CACHE_ENABLED and cached_catalog is not None:
        return cached_catalog
    async with cache_lock:
        if CACHE_ENABLED and cached_catalog is not None:
            return cached_catalog
        async with measure(request, "catalogo"):
            response = await request.app.state.http.get(
                f"{CATALOG}/catalogo", headers={HEADER: request.state.correlation})
            response.raise_for_status()
            value = response.json()
            if value.get("version") != DATASET:
                raise HTTPException(503, "Synthetic dataset version mismatch")
        if CACHE_ENABLED:
            cached_catalog = value
        return value


async def source(request):
    async with measure(request, "simulador"):
        # No retener una conexión SQL durante la espera externa.
        response = await request.app.state.http.get(
            f"{SOURCE}/fuente", headers={HEADER: request.state.correlation}, timeout=TIMEOUT)
        response.raise_for_status()
        return response


@app.post("/cotizaciones", status_code=201)
async def quote(body: QuoteInput, request: Request):
    # catalog() no depende de la fuente externa; solo importa con caché fría
    # (RULES_CACHE_ENABLED=false o la primera solicitud de la tarea), ya que
    # con caché tibia catalog() no hace E/S real.
    rules, response = await asyncio.gather(catalog(request), source(request))
    payload = {
        "id": str(uuid4()), "product_id": body.product_id,
        "dataset": DATASET, "rules_version": rules["version"],
        "result": "synthetic", "source": response.json(),
    }
    await fetch_one(request,
        "INSERT INTO experiment_quotes (id, dataset, payload) VALUES (%s, %s, %s) RETURNING id",
        (payload["id"], DATASET, Jsonb(payload)))
    return payload


@app.get("/cotizaciones/{quote_id}")
async def get_quote(quote_id: str, request: Request):
    row = await fetch_one(request,
        "SELECT payload FROM experiment_quotes WHERE id = %s AND dataset = %s", (quote_id, DATASET))
    if row is None:
        raise HTTPException(404, "Synthetic quotation not found")
    return row["payload"]


@app.get("/health")
async def health(request: Request):
    await fetch_one(request, "SELECT id FROM experiment_quotes LIMIT 1")
    await catalog(request)
    return {"status": "ok"}
