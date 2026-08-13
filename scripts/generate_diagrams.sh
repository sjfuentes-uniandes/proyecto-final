#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIAGRAM_DIR="${ROOT_DIR}/docs/diagramas"
OUTPUT_DIR="${DIAGRAM_DIR}/generated"

mkdir -p "${OUTPUT_DIR}"

# Build the local image once so the project is reproducible and easy to run.
docker build -t proyecto-final-diagramas "${ROOT_DIR}" >/dev/null

docker run --rm \
  -v "${ROOT_DIR}:/work" \
  -w /work \
  proyecto-final-diagramas \
  -tsvg \
  -tpng \
  -o /work/docs/diagramas/generated \
  /work/docs/diagramas/*.puml

printf '\nDiagramas generados en: %s\n' "${OUTPUT_DIR}"
