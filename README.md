# proyecto Final
Repositorio para actividades del proyecto final

## Diagramas PlantUML

Este repositorio incluye diagramas en formato PlantUML dentro de `docs/diagramas`. Para generar las versiones PNG/SVG y dejar las imágenes en `docs/diagramas/generated`, se usa Docker con la imagen oficial de PlantUML.

### Requisitos

- Docker instalado y en ejecución
- Git

### Generar diagramas

Ejecuta cualquiera de estas opciones desde la raíz del proyecto:

```bash
./scripts/generate_diagrams.sh
```

O con Make:

```bash
make diagrams
```

Esto recorrerá todos los archivos `.puml` y generará las imágenes en la carpeta `docs/diagramas/generated`.

### Generar automáticamente al detectar cambios

Si quieres que se regeneren las imágenes cada vez que cambie un diagrama, puedes usar:

```bash
make watch-diagramas
```

Esto requiere `fswatch`, que se puede instalar en macOS con:

```bash
brew install fswatch
```

### Estructura relevante

```text
.
├── Dockerfile
├── Makefile
├── scripts/
│   └── generate_diagrams.sh
├── docs/
│   └── diagramas/
│       ├── *.puml
│       └── generated/
```

### Ejemplo de flujo de trabajo

```bash
# 1. editar un archivo .puml
# 2. regenerar imágenes
make diagrams

# o dejarlo escuchando cambios
make watch-diagramas
```

Las imágenes generadas quedan listas para versionar y también pueden mostrarse en documentación o README.
