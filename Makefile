.PHONY: diagrams watch-diagramas

DIAGRAM_DIR := docs/diagramas

diagrams:
	@./scripts/generate_diagrams.sh

watch-diagramas:
	@command -v fswatch >/dev/null 2>&1 || { echo "Falta fswatch. Instálalo con: brew install fswatch"; exit 1; }
	@fswatch -o $(DIAGRAM_DIR) | xargs -n1 -I{} make diagrams
