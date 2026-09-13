#!/usr/bin/env bash
set -euo pipefail

# Destruye el ambiente en orden inverso al despliegue: primero infra/services,
# después infra/base (incluye los repositorios ECR: usan force_delete). Ver
# README.md, sección 12. Irreversible: RDS no conserva snapshot final.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

command -v terraform >/dev/null 2>&1 || { echo "Falta terraform."; exit 1; }

# terraform apply -destroy sin -out ni -auto-approve: siempre muestra el plan
# de destrucción y hace la única pregunta de este script (aprobarlo).
# SOLVENTA_YES=1 la omite.
tf_destroy() {
  if [ "${SOLVENTA_YES:-0}" = "1" ]; then
    terraform -chdir="$1" apply -destroy -auto-approve
  else
    terraform -chdir="$1" apply -destroy
  fi
}

echo "==> 1/2 Destruir infra/services"
tf_destroy infra/services

echo "==> 2/2 Destruir infra/base"
tf_destroy infra/base

echo "Destrucción completa."
