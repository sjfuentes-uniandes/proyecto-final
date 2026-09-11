from fastapi import HTTPException, Request
from common.runtime import DATASET, create_app, fetch_one

app = create_app(database=True)


@app.get("/consultas")
async def query_default(request: Request):
    return await query_policy("poliza-000001", request)


@app.get("/consultas/{policy_id}")
async def query_policy(policy_id: str, request: Request):
    row = await fetch_one(request,
        "SELECT payload FROM experiment_projection WHERE dataset = %s AND policy_id = %s",
        (DATASET, policy_id))
    if row is None:
        raise HTTPException(404, "Synthetic policy not found")
    return row["payload"]


@app.get("/health")
async def health(request: Request):
    row = await fetch_one(request,
        "SELECT policy_id FROM experiment_projection WHERE dataset = %s AND policy_id = %s",
        (DATASET, "poliza-000001"))
    if row is None:
        raise HTTPException(503, "Synthetic dataset not loaded")
    return {"status": "ok"}
