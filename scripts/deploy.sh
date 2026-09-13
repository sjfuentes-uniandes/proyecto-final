#!/usr/bin/env bash
set -euo pipefail

# Despliega el ambiente completo: infra/base, publicación de imágenes (solo
# build+push) e infra/services, y ejecuta el seed inicial (README.md,
# secciones 3-7). No incluye la espera de services-stable ni smoke (secciones 8-9).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

command -v terraform >/dev/null 2>&1 || { echo "Falta terraform."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "Falta docker."; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "Falta jq."; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "Falta AWS CLI v2."; exit 1; }

# terraform apply sin -out ni -auto-approve: siempre muestra el plan y hace la
# única pregunta de este script (aprobar ese plan). SOLVENTA_YES=1 la omite.
tf_apply() {
  if [ "${SOLVENTA_YES:-0}" = "1" ]; then
    terraform -chdir="$1" apply -auto-approve
  else
    terraform -chdir="$1" apply
  fi
}

echo "==> 1/4 Infraestructura base (infra/base)"

if [ ! -f infra/base/terraform.tfvars ]; then
  cp infra/base/terraform.tfvars.example infra/base/terraform.tfvars
  echo "Creado infra/base/terraform.tfvars a partir del ejemplo; revisar aws_region/name antes de continuar."
fi

terraform -chdir=infra/base init -input=false
tf_apply infra/base

SOLVENTA_REPOSITORIES=$(terraform -chdir=infra/base output -json ecr_repositories)
SOLVENTA_CONFIGURATION=$(terraform -chdir=infra/base output -json foundation)
SOLVENTA_REGION=$(jq -er '.region' <<< "${SOLVENTA_CONFIGURATION}")
SOLVENTA_CLUSTER=$(jq -er '.cluster.name' <<< "${SOLVENTA_CONFIGURATION}")
SOLVENTA_REGISTRY=$(jq -er '.catalogo | split("/")[0]' <<< "${SOLVENTA_REPOSITORIES}")
export AWS_REGION="${SOLVENTA_REGION}"

echo "==> 2/4 Publicar imágenes en ECR (build + push)"

aws ecr get-login-password --region "${SOLVENTA_REGION}" |
  docker login --username AWS --password-stdin "${SOLVENTA_REGISTRY}"

SOLVENTA_IMAGE_TAG="exp-$(date -u +%Y%m%dT%H%M%SZ)"
for SOLVENTA_SERVICE in catalogo simulador consulta cotizacion; do
  SOLVENTA_REPOSITORY=$(jq -er --arg service "${SOLVENTA_SERVICE}" '.[$service]' <<< "${SOLVENTA_REPOSITORIES}")
  echo "    - ${SOLVENTA_SERVICE} -> ${SOLVENTA_REPOSITORY}:${SOLVENTA_IMAGE_TAG}"
  docker buildx build \
    --platform linux/amd64 \
    --provenance=false \
    --file "src/${SOLVENTA_SERVICE}/Dockerfile" \
    --tag "${SOLVENTA_REPOSITORY}:${SOLVENTA_IMAGE_TAG}" \
    --push src
done

SOLVENTA_DIGESTS='{}'
for SOLVENTA_SERVICE in catalogo simulador consulta cotizacion; do
  SOLVENTA_REPOSITORY=$(jq -er --arg service "${SOLVENTA_SERVICE}" '.[$service]' <<< "${SOLVENTA_REPOSITORIES}")
  SOLVENTA_REPOSITORY_NAME=${SOLVENTA_REPOSITORY#*/}
  SOLVENTA_DIGEST=$(aws ecr describe-images \
    --region "${SOLVENTA_REGION}" \
    --repository-name "${SOLVENTA_REPOSITORY_NAME}" \
    --image-ids "imageTag=${SOLVENTA_IMAGE_TAG}" \
    --query 'imageDetails[0].imageDigest' --output text)
  SOLVENTA_DIGESTS=$(jq --arg service "${SOLVENTA_SERVICE}" --arg digest "${SOLVENTA_DIGEST}" \
    '. + {($service): $digest}' <<< "${SOLVENTA_DIGESTS}")
done
jq -n --argjson digests "${SOLVENTA_DIGESTS}" '{image_digests: $digests}' \
  > infra/services/images.auto.tfvars.json
echo "Digests publicados:"
cat infra/services/images.auto.tfvars.json

echo "==> 3/4 Servicios de aplicación (infra/services)"

if [ ! -f infra/services/terraform.tfvars ]; then
  cp infra/services/terraform.tfvars.example infra/services/terraform.tfvars
  echo "Creado infra/services/terraform.tfvars a partir del ejemplo; revisar antes de continuar."
fi

terraform -chdir=infra/services init -input=false
tf_apply infra/services

echo "==> 4/4 Seed inicial (tablas, catálogo y 1.000 pólizas sintéticas)"

SOLVENTA_SEED=$(terraform -chdir=infra/services output -json seed_task)
SOLVENTA_SEED_DEFINITION=$(jq -er '.task_definition' <<< "${SOLVENTA_SEED}")
if [ "${SOLVENTA_SEED_DEFINITION}" = "null" ]; then
  echo "seed_task.task_definition es null: configurar seed_command en infra/services y aplicar antes de sembrar."
  exit 1
fi
SOLVENTA_SEED_NETWORK=$(jq -c '{awsvpcConfiguration: {
  subnets: [.subnet], securityGroups: [.security_group], assignPublicIp: "ENABLED"
}}' <<< "${SOLVENTA_SEED}")

SOLVENTA_SEED_RESULT=$(aws ecs run-task \
  --cluster "${SOLVENTA_CLUSTER}" \
  --launch-type FARGATE \
  --platform-version 1.4.0 \
  --task-definition "${SOLVENTA_SEED_DEFINITION}" \
  --network-configuration "${SOLVENTA_SEED_NETWORK}" \
  --count 1 --output json)
echo "${SOLVENTA_SEED_RESULT}" | jq '{failures, tasks: [.tasks[] | {taskArn, lastStatus}]}'
jq -e '(.failures | length) == 0 and (.tasks | length) == 1' <<< "${SOLVENTA_SEED_RESULT}" >/dev/null
SOLVENTA_SEED_TASK=$(jq -er '.tasks[0].taskArn' <<< "${SOLVENTA_SEED_RESULT}")

aws ecs wait tasks-stopped --cluster "${SOLVENTA_CLUSTER}" --tasks "${SOLVENTA_SEED_TASK}"
SOLVENTA_SEED_STATUS=$(aws ecs describe-tasks \
  --cluster "${SOLVENTA_CLUSTER}" --tasks "${SOLVENTA_SEED_TASK}" --output json)
echo "${SOLVENTA_SEED_STATUS}" | jq '.tasks[0] | {stoppedReason, containers}'
if ! jq -e '(.failures | length) == 0 and
  any(.tasks[0].containers[]; .name == "seed" and .exitCode == 0)' <<< "${SOLVENTA_SEED_STATUS}" >/dev/null; then
  echo "El seed no terminó con exitCode 0. Revisar la salida anterior antes de continuar."
  exit 1
fi

cat <<'NEXT'

Despliegue, publicación de imágenes y seed inicial completos.
Pendiente (no incluido en este target): esperar services-stable y correr las
pruebas smoke. Ver README.md secciones 8-9.
NEXT
