.PHONY: diagrams watch-diagramas deploy experiment-clean-up destroy

DIAGRAM_DIR := docs/diagramas

diagrams:
	@./scripts/generate_diagrams.sh

watch-diagramas:
	@command -v fswatch >/dev/null 2>&1 || { echo "Falta fswatch. Instálalo con: brew install fswatch"; exit 1; }
	@fswatch -o $(DIAGRAM_DIR) | xargs -n1 -I{} make diagrams

# Despliega infra/base, publica las imágenes (build+push), aplica infra/services
# y ejecuta el seed inicial. No incluye espera de servicios ni smoke: ver
# README.md secciones 8-9.
deploy:
	@./scripts/deploy.sh

# Reset transaccional de la BD antes de cada repetición de EXP-ESC-01
# (experiments/exp-esc-01/README.md, secciones 2-3).
experiment-clean-up:
	@./scripts/experiment_reset.sh

# Destruye infra/services y luego infra/base, en orden inverso al deploy.
# Cada terraform apply -destroy muestra su plan y pregunta; SOLVENTA_YES=1
# la omite (-auto-approve) para ejecución no interactiva.
destroy:
	@./scripts/destroy.sh
