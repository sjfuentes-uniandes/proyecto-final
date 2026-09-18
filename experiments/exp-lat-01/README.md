# EXP-LAT-01 — Latencia de cotización y consulta

Mide simultáneamente `POST /cotizaciones` y `GET /consultas/poliza-000001` a **500 solicitudes/minuto por endpoint**, durante diez minutos. Se realizan tres repeticiones y se aprueba solamente cuando las tres son completas: cotización p95 ≤ 250 ms, consulta p95 ≤ 150 ms y errores técnicos ≤ 1 %.

## Responsabilidades y precondiciones

Este directorio no despliega ni altera AWS. El responsable de infraestructura debe aplicar el escenario fijo siguiente antes de cada serie:

```bash
terraform -chdir=infra/services apply \
  -var='quotation_replicas=1' \
  -var='quotation_autoscaling_enabled=false' \
  -var='backend_autoscaling_enabled=false'
```

Debe publicar una sola tanda de digests ECR, ejecutar seed y confirmar: cuatro servicios sanos, una tarea por servicio, ambos target groups sanos, simulador a 50 ms y `FAILURE_RATE=0`. El operador de pruebas necesita AWS de solo lectura, Terraform, AWS CLI v2, Python 3.9+ y k6.

Antes de **cada** repetición, detener clientes, esperar estabilidad y pedir al responsable con permisos que ejecute el reset sintético documentado en [EXP-ESC-01](../exp-esc-01/README.md#reiniciar-la-base-desde-la-cli-antes-de-cada-repetición). No ejecutar POST manuales después del reset.

## Ejecución

Desde la raíz del repositorio, tras confirmar el reset correspondiente:

```bash
python3 experiments/exp-lat-01/run.py \
  --series lat-001 --repetition 1 \
  --dataset-state "synthetic-v1; reset <TASK_ID> confirmado: 0 cotizaciones, 1000 pólizas, 1 catálogo"
```

Repetir con `--repetition 2` y `3`, ejecutando un reset y dejando 2–3 minutos de enfriamiento antes de cada una. El runner obtiene `BASE_URL` desde los outputs Terraform, valida la configuración fija, snapshots ECS/ALB, definición de tarea y digest antes de iniciar k6. No sobrescribe evidencia existente.

Tras cada repetición, esperar unos minutos por CloudWatch y recopilar:

```bash
python3 experiments/exp-lat-01/collect.py experiments/exp-lat-01/results/lat-001
```

Al completar las tres:

```bash
python3 experiments/exp-lat-01/summarize.py experiments/exp-lat-01/results/lat-001
```

El resultado queda en `report.md` y `report.json`. Cada `run-N/` conserva configuración, snapshots antes/después, salida k6, resumen por endpoint y métricas CloudWatch. `results/` está ignorado por Git; guardar o adjuntar esa carpeta antes de destruir EXP.

## Interpretación

Un resultado con iteraciones descartadas, volumen incompleto o una consulta AWS fallida no es una prueba válida. Si el umbral falla, correlacionar `cloudwatch.json` y logs de `cotizacion`, `consulta`, `catalogo`, `simulador`, RDS, ALB y API Gateway antes de atribuir la causa a caché, pool RDS, serialización, dependencia externa o gateway.
