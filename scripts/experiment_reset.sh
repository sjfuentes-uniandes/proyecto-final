#!/usr/bin/env bash
set -euo pipefail

# Reset transaccional de la BD antes de cada repetición de EXP-ESC-01.
# Puerto fiel de experiments/exp-esc-01/README.md, secciones 2-3: espera el
# punto inicial (4 tareas saludables), trunca y recarga catálogo/pólizas
# sintéticas en una transacción y verifica RESET_OK + exitCode 0.
#
# Detener antes cualquier cliente (k6, smoke) que siga escribiendo.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

command -v terraform >/dev/null 2>&1 || { echo "Falta terraform."; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "Falta AWS CLI v2."; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "Falta jq."; exit 1; }

echo "==> 1/4 Esperar el punto inicial (cuatro servicios desired=running=1, pending=0)"

SOLVENTA_SEED=$(terraform -chdir=infra/services output -json seed_task)
SOLVENTA_CLUSTER=$(jq -er '.cluster' <<< "${SOLVENTA_SEED}")
SOLVENTA_DEFINITION=$(jq -er '.task_definition' <<< "${SOLVENTA_SEED}")
SOLVENTA_REGION=$(terraform -chdir=infra/services output -json experiment_configuration | jq -er '.region')

if [ "${SOLVENTA_DEFINITION}" = "null" ]; then
  echo "seed_task.task_definition es null: configurar seed_command y aplicar infra/services antes de resetear."
  exit 1
fi

SOLVENTA_NETWORK=$(jq -c '{
  awsvpcConfiguration: {
    subnets: [.subnet],
    securityGroups: [.security_group],
    assignPublicIp: "ENABLED"
  }
}' <<< "${SOLVENTA_SEED}")

SOLVENTA_WAIT_ATTEMPTS="${SOLVENTA_WAIT_ATTEMPTS:-10}"
for _ in $(seq 1 "${SOLVENTA_WAIT_ATTEMPTS}"); do
  aws ecs wait services-stable \
    --region "${SOLVENTA_REGION}" --cluster "${SOLVENTA_CLUSTER}" \
    --services catalogo simulador consulta cotizacion

  SOLVENTA_COUNTS=$(aws ecs describe-services \
    --region "${SOLVENTA_REGION}" --cluster "${SOLVENTA_CLUSTER}" \
    --services catalogo simulador consulta cotizacion \
    --query 'services[].{service:serviceName,desired:desiredCount,running:runningCount,pending:pendingCount}' \
    --output json)
  echo "${SOLVENTA_COUNTS}" | jq .

  if jq -e 'all(.[]; .desired == 1 and .running == 1 and .pending == 0)' <<< "${SOLVENTA_COUNTS}" >/dev/null; then
    SOLVENTA_AT_REST=1
    break
  fi
  echo "Todavía no es el punto inicial (autoscaling reduciendo tareas); reintentando..."
  sleep 15
done

if [ "${SOLVENTA_AT_REST:-0}" != "1" ]; then
  echo "No se alcanzó desired=running=1 en ${SOLVENTA_WAIT_ATTEMPTS} intentos. Revisar eventos/salud antes de resetear."
  exit 1
fi

echo "==> 2/4 Preparar el reset transaccional"

SOLVENTA_RESET_CODE=$(cat <<'PY'
import psycopg
from common.runtime import database_options
from psycopg.types.json import Jsonb

with psycopg.connect(**database_options()) as connection:
    connection.execute("SELECT pg_advisory_xact_lock(58001)")
    connection.execute("""
        TRUNCATE TABLE
            experiment_quotes,
            experiment_projection,
            experiment_catalog
    """)
    connection.execute(
        "INSERT INTO experiment_catalog VALUES (%s, %s)",
        ("synthetic-v1", Jsonb({
            "version": "synthetic-v1",
            "products": ["producto-sintetico"],
            "rules": {"mode": "synthetic-no-business-logic"}
        }))
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO experiment_projection VALUES (%s, %s, %s)",
            [
                ("synthetic-v1", f"poliza-{i:06d}", Jsonb({
                    "id": f"poliza-{i:06d}",
                    "dataset": "synthetic-v1",
                    "status": "synthetic",
                    "coverage": "test-only"
                }))
                for i in range(1, 1001)
            ]
        )
    for table, expected in (
        ("experiment_quotes", 0),
        ("experiment_projection", 1000),
        ("experiment_catalog", 1),
    ):
        total = connection.execute(f"SELECT count(*) AS total FROM {table}").fetchone()["total"]
        if total != expected:
            raise RuntimeError(f"{table}: {total} registros; esperados {expected}")
        print(table, total)

print("RESET_OK")
PY
)

SOLVENTA_OVERRIDES=$(jq -n --arg code "${SOLVENTA_RESET_CODE}" '{
  containerOverrides: [{
    name: "seed",
    command: ["python", "-c", $code]
  }]
}')

echo "==> 3/4 Ejecutar la tarea de reset"

SOLVENTA_RESULT=$(aws ecs run-task \
  --region "${SOLVENTA_REGION}" \
  --cluster "${SOLVENTA_CLUSTER}" \
  --launch-type FARGATE \
  --platform-version 1.4.0 \
  --task-definition "${SOLVENTA_DEFINITION}" \
  --network-configuration "${SOLVENTA_NETWORK}" \
  --overrides "${SOLVENTA_OVERRIDES}" \
  --count 1 \
  --output json)

printf '%s\n' "${SOLVENTA_RESULT}" | jq '{failures, tasks: [.tasks[].taskArn]}'
printf '%s\n' "${SOLVENTA_RESULT}" | jq -e \
  '(.failures | length) == 0 and (.tasks | length) == 1' >/dev/null
SOLVENTA_TASK=$(printf '%s\n' "${SOLVENTA_RESULT}" | jq -er '.tasks[0].taskArn')

echo "==> 4/4 Esperar y verificar el resultado"

aws ecs wait tasks-stopped \
  --region "${SOLVENTA_REGION}" \
  --cluster "${SOLVENTA_CLUSTER}" \
  --tasks "${SOLVENTA_TASK}"

SOLVENTA_RESET_STATUS=$(aws ecs describe-tasks \
  --region "${SOLVENTA_REGION}" \
  --cluster "${SOLVENTA_CLUSTER}" \
  --tasks "${SOLVENTA_TASK}" \
  --output json)

printf '%s\n' "${SOLVENTA_RESET_STATUS}" | jq \
  '.tasks[0] | {stoppedReason, containers: [.containers[] | {name, exitCode, reason}]}'

if ! printf '%s\n' "${SOLVENTA_RESET_STATUS}" | jq -e \
  '(.failures | length) == 0 and any(.tasks[0].containers[]; .name == "seed" and .exitCode == 0)' >/dev/null; then
  SOLVENTA_CLUSTER_NAME="${SOLVENTA_CLUSTER##*/}"
  SOLVENTA_TASK_ID="${SOLVENTA_TASK##*/}"
  echo "El reset no terminó con exitCode 0. Logs de esta ejecución:"
  aws logs tail "/ecs/${SOLVENTA_CLUSTER_NAME}/catalogo" \
    --region "${SOLVENTA_REGION}" \
    --log-stream-names "app/seed/${SOLVENTA_TASK_ID}" \
    --since 15m --format short || true
  exit 1
fi

SOLVENTA_CLUSTER_NAME="${SOLVENTA_CLUSTER##*/}"
SOLVENTA_TASK_ID="${SOLVENTA_TASK##*/}"

SOLVENTA_RESET_EVIDENCE="experiments/exp-esc-01/results/resets/$(date -u +%Y%m%dT%H%M%SZ)-${SOLVENTA_TASK_ID}"
mkdir -p "${SOLVENTA_RESET_EVIDENCE}"
printf '%s\n' "${SOLVENTA_RESET_STATUS}" > "${SOLVENTA_RESET_EVIDENCE}/task.json"

echo
echo "RESET_OK — tarea ${SOLVENTA_TASK_ID}"
echo "Evidencia guardada en ${SOLVENTA_RESET_EVIDENCE}/task.json"
echo "Usar este SOLVENTA_TASK_ID en --dataset-state de la siguiente repetición."
