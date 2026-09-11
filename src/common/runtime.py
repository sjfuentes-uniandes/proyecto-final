import json
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import psycopg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout, TooManyRequests

SERVICE = os.getenv("SERVICE_NAME", "experiment")
DATASET = os.getenv("DATASET_VERSION", "synthetic-v1")
HEADER = os.getenv("CORRELATION_HEADER", "X-Correlation-Id")


def log(event, **fields):
    print(json.dumps({"event": event, "service": SERVICE, **fields}), flush=True)


def database_options():
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "solventa"),
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "sslmode": os.getenv("DB_SSLMODE", "require"),
        "connect_timeout": 5,
        "options": "-c statement_timeout=2000",
        "row_factory": dict_row,
    }


def create_app(database=False):
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            timeout=2.0, limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
        ) as client:
            app.state.http = client
            if database:
                size = int(os.getenv("DB_POOL_SIZE", "5"))
                pool = AsyncConnectionPool(
                    kwargs=database_options(), min_size=1, max_size=size,
                    timeout=2, max_waiting=200, open=False,
                )
                app.state.pool = pool
                try:
                    await pool.open(wait=True, timeout=20)
                    yield
                finally:
                    await pool.close()
            else:
                yield

    app = FastAPI(title=SERVICE, lifespan=lifespan)

    @app.middleware("http")
    async def telemetry(request: Request, call_next):
        correlation = request.headers.get(HEADER, str(uuid4()))[:128]
        request.state.correlation = correlation
        request.state.timings = {}
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[HEADER] = correlation
            return response
        finally:
            log("request", correlation_id=correlation, method=request.method,
                path=request.url.path, status=status,
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
                dependencies_ms=request.state.timings)

    async def unavailable(request: Request, error):
        # No incluir credenciales, SQL ni cuerpos de solicitudes en los errores.
        log("dependency_error", correlation_id=request.state.correlation,
            error_type=type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "Dependency unavailable"})

    for error in (psycopg.Error, PoolTimeout, TooManyRequests, httpx.HTTPError):
        app.add_exception_handler(error, unavailable)
    return app


@asynccontextmanager
async def measure(request, dependency):
    start = time.perf_counter()
    try:
        yield
    finally:
        request.state.timings[dependency] = round((time.perf_counter() - start) * 1000, 3)


async def fetch_one(request, sql, params=()):
    async with measure(request, "postgresql"):
        async with request.app.state.pool.connection() as connection:
            cursor = await connection.execute(sql, params)
            return await cursor.fetchone()
