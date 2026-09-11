"""Carga sintética explícita e idempotente. No borra cotizaciones existentes."""
import argparse
import psycopg
from psycopg.types.json import Jsonb
from common.runtime import database_options, log


def seed(dataset):
    with psycopg.connect(**database_options()) as connection:
        # Una única transacción, incluso con ejecuciones concurrentes.
        connection.execute("SELECT pg_advisory_xact_lock(58001)")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_catalog (
            version text PRIMARY KEY, payload jsonb NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_projection (
            dataset text NOT NULL, policy_id text NOT NULL, payload jsonb NOT NULL,
            PRIMARY KEY (dataset, policy_id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_quotes (
            id text PRIMARY KEY, dataset text NOT NULL, payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now())""")
        connection.execute("""INSERT INTO experiment_catalog VALUES (%s, %s)
            ON CONFLICT (version) DO UPDATE SET payload = EXCLUDED.payload""",
            (dataset, Jsonb({"version": dataset, "products": ["producto-sintetico"],
                            "rules": {"mode": "synthetic-no-business-logic"}})))
        with connection.cursor() as cursor:
            cursor.executemany("""INSERT INTO experiment_projection VALUES (%s, %s, %s)
                ON CONFLICT (dataset, policy_id) DO UPDATE SET payload = EXCLUDED.payload""",
                [(dataset, f"poliza-{i:06d}", Jsonb({"id": f"poliza-{i:06d}",
                  "dataset": dataset, "status": "synthetic", "coverage": "test-only"}))
                 for i in range(1, 1001)])
    log("seed_complete", dataset=dataset, policies=1000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="synthetic-v1", choices=["synthetic-v1"])
    seed(parser.parse_args().dataset)
