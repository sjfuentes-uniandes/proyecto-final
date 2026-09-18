# EXP-DIS-01 — Disponibilidad ante detención de una tarea ECS

Evalúa cotización con dos tareas Fargate. k6 mantiene 150 solicitudes/minuto: tres minutos de baseline y tres minutos de perturbación. La hipótesis se aprueba en tres corridas completas cuando, durante la perturbación, el éxito es ≥ 99 %, p95 ≤ 500 ms y el retorno a dos destinos saludables toma ≤ 120 s.

## Preparación y autorización

El responsable de infraestructura debe aplicar antes de la serie:

```bash
terraform -chdir=infra/services apply \
  -var='quotation_replicas=2' \
  -var='quotation_autoscaling_enabled=false' \
  -var='backend_autoscaling_enabled=false'
```

Luego debe confirmar una tarea en `catalogo`, `simulador` y `consulta`, dos en `cotizacion`, y dos destinos `healthy` en su target group. Antes de cada repetición se ejecuta el reset sintético de [EXP-ESC-01](../exp-esc-01/README.md#reiniciar-la-base-desde-la-cli-antes-de-cada-repetición).

`run.py` ejecuta `ecs stop-task` exactamente al final del baseline y requiere permiso `ecs:StopTask` sobre la tarea indicada. Un acceso AWS solo de lectura no puede completar la corrida: el responsable con permisos debe lanzar el comando, o prestar una identidad temporal limitada a esta acción y al clúster del experimento.

## Ejecución

Consultar las dos tareas de cotización sanas y seleccionar una de ellas:

```bash
aws ecs list-tasks --cluster solventa-exp --service-name cotizacion --desired-status RUNNING
```

Después del reset validado, ejecutar:

```bash
python3 experiments/exp-dis-01/run.py \
  --series dis-001 --repetition 1 \
  --fault-task-arn '<TASK_ARN_DE_COTIZACION>' \
  --dataset-state "synthetic-v1; reset <TASK_ID> confirmado: 0 cotizaciones, 1000 pólizas, 1 catálogo"
```

El runner rechaza una tarea que no pertenezca a `cotizacion`, crea `t0` justo antes del `stop-task`, sondea ECS y el target group cada cinco segundos y escribe `t1` al recuperar `desired=2`, `running=2`, `pending=0` y dos destinos sanos. No detener k6 ni modificar la topología durante la ejecución.

Esperar estabilización, resetear y repetir con `--repetition 2` y `3`. Después de cada corrida:

```bash
python3 experiments/exp-dis-01/collect.py experiments/exp-dis-01/results/dis-001
```

Al finalizar:

```bash
python3 experiments/exp-dis-01/summarize.py experiments/exp-dis-01/results/dis-001
```

`report.md` y `report.json` contienen resultados individuales, medianas, RTO y el estado de la hipótesis. Revisar además `timeline.json`, `stop-task.json`, logs ECS, eventos y CloudWatch. Si no se recupera dentro de la ventana, el RTO queda inconcluso: conservar la evidencia y recuperar el servicio antes de iniciar otra repetición.
