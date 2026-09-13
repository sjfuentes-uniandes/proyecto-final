# EXP-ESC-01 — Escalamiento automático de cotización

El experimento actual evalúa una política de **autoscaling de 1 a 3 tareas de cotización**, mientras aumenta la carga de 500 a 50.000 solicitudes/minuto. Se realizan **tres repeticiones de la misma política**. Cada repetición incluye todos los niveles de carga, salvo que se active el corte de protección.

El criterio de aceptación por meseta es **p95 ≤ 250 ms y errores ≤ 1 %**, con el volumen de carga completo. La prueba usa el `POST /cotizaciones` del prototipo a través de API Gateway y genera datos sintéticos persistidos.


## Orden de ejecución y momento de cada reset

Ejecutar los comandos desde la raíz del repositorio. Una serie, por ejemplo `auto-001`, contiene las repeticiones 1, 2 y 3.

| Momento | Qué hacer |
| --- | --- |
| Una vez, antes de la serie | Aplicar la política de autoscaling, comprobar credenciales, seed inicial y funcionamiento de servicios. Ejecutar las pruebas smoke aquí, antes del primer reset. |
| Antes de repetición 1 | Detener clientes, esperar una tarea de cotización saludable, ejecutar reset 1 y confirmar `RESET_OK` y salida 0. Iniciar repetición 1. |
| Al terminar repetición 1 | Conservar evidencias y recolectar métricas. Esperar que terminen solicitudes pendientes y que autoscaling vuelva a una tarea saludable. Ejecutar reset 2 e iniciar repetición 2. |
| Al terminar repetición 2 | Conservar evidencias y recolectar métricas. Esperar nuevamente el estado inicial. Ejecutar reset 3 e iniciar repetición 3. |
| Al terminar repetición 3 | Recolectar métricas y consolidar los resultados. No hace falta otro reset para terminar la serie. |

**Son tres resets: uno inmediatamente antes de cada repetición. No resetear entre rampas o mesetas, durante la carga ni mientras queden escrituras pendientes.** El crecimiento de la BD dentro de cada repetición forma parte del ensayo. El runner no resetea la base ni inicia la siguiente repetición automáticamente.

Si una repetición se detiene por protección, también hay que esperar recuperación y resetear antes de la siguiente. Conservar la ejecución fallida; no sustituirla por un reintento exitoso. Si cambias imágenes, tamaño, perfil o política para corregir el problema, comenzar otra serie.

## 1. Preparar el ambiente y aplicar la política

Requisitos:

- Ambiente desplegado según el [README principal](../../README.md), con seed inicial exitoso y cuatro servicios saludables.
- k6 2.1, Python 3.10+, Terraform, AWS CLI v2 y jq.
- Credenciales vigentes durante toda la ejecución. El runner consulta ECS/ELB y actividades de Application Auto Scaling; el recolector consulta CloudWatch. Para el reset se necesitan además permisos para lanzar la tarea seed y pasar sus roles IAM.
- Misma máquina/red generadora, digests, CPU/memoria por tarea, pool, zona, dataset y política en las tres repeticiones. Simulador con latencia de 50 ms y `FAILURE_RATE=0`.


## 2. Recuperar el punto inicial antes de cada reset

Detener k6 y cualquier cliente que escriba. Esperar que se vacíen las solicitudes pendientes, incluso las que el cliente abandonó por timeout. Revisar logs si sigue habiendo actividad. Después consultar:

```bash
aws ecs wait services-stable \
  --region "$SOLVENTA_REGION" --cluster "$SOLVENTA_CLUSTER" \
  --services catalogo simulador consulta cotizacion

aws ecs describe-services \
  --region "$SOLVENTA_REGION" --cluster "$SOLVENTA_CLUSTER" \
  --services catalogo simulador consulta cotizacion \
  --query 'services[].{service:serviceName,desired:desiredCount,running:runningCount,pending:pendingCount}'
```

Los cuatro servicios deben tener `desired=1`, `running=1` y `pending=0`. **El waiter puede terminar con dos o tres tareas estables: eso todavía no es el punto inicial.** Esperar la reducción automática y repetir la consulta. El runner verifica además la salud de contenedores y destinos ALB antes de generar carga.

Si el servicio no se recupera, revisar eventos y logs antes de continuar. Reiniciar la base no soluciona un problema de salud, red o credenciales. No desactivar la política ni reducir tareas durante una repetición.

## Reiniciar la base desde la CLI antes de cada repetición

Ejecutar estos pasos desde la raíz del repositorio, con las credenciales AWS del ambiente. **El reset elimina todas las cotizaciones y restablece catálogo y pólizas sintéticas.** Guardar primero las evidencias y detener k6 y cualquier otro cliente que escriba. Esperar que terminen las solicitudes pendientes antes del reset.

No requiere reconstruir imágenes: usa la definición de tarea seed existente con un comando sobrescrito. Las tablas deben existir por la carga inicial. Ejecutar todos los bloques en la misma terminal. Si un comando falla, detenerse y revisar el error antes de continuar.

### 1. Obtener la tarea y su red

```bash
SOLVENTA_SEED=$(terraform -chdir=infra/services output -json seed_task)
SOLVENTA_CLUSTER=$(printf '%s\n' "$SOLVENTA_SEED" | jq -er '.cluster')
SOLVENTA_DEFINITION=$(printf '%s\n' "$SOLVENTA_SEED" | jq -er '.task_definition')
SOLVENTA_REGION=$(terraform -chdir=infra/services output -json experiment_configuration | jq -er '.region')

SOLVENTA_NETWORK=$(printf '%s\n' "$SOLVENTA_SEED" | jq -c '{
  awsvpcConfiguration: {
    subnets: [.subnet],
    securityGroups: [.security_group],
    assignPublicIp: "ENABLED"
  }
}')
```

Si `task_definition` es `null`, configurar `seed_command` y desplegar su definición en `infra/services` según el README principal. No continuar sin una definición válida.

### 2. Preparar el reset transaccional

```bash
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

SOLVENTA_OVERRIDES=$(jq -n --arg code "$SOLVENTA_RESET_CODE" '{
  containerOverrides: [{
    name: "seed",
    command: ["python", "-c", $code]
  }]
}')
```

El borrado, la recarga y la comprobación se realizan en una transacción; si falla, se revierte. `RESET_OK` se imprime después del commit. Se usa `printf '%s\n'` para preservar el JSON: `echo` puede interpretar escapes en Zsh y provocar el error `Invalid string: control characters`.

### 3. Ejecutar una sola tarea de reset

```bash
SOLVENTA_RESULT=$(aws ecs run-task \
  --region "$SOLVENTA_REGION" \
  --cluster "$SOLVENTA_CLUSTER" \
  --launch-type FARGATE \
  --platform-version 1.4.0 \
  --task-definition "$SOLVENTA_DEFINITION" \
  --network-configuration "$SOLVENTA_NETWORK" \
  --overrides "$SOLVENTA_OVERRIDES" \
  --count 1 \
  --output json)

printf '%s\n' "$SOLVENTA_RESULT" | jq '{failures, tasks: [.tasks[].taskArn]}'
printf '%s\n' "$SOLVENTA_RESULT" | jq -e \
  '(.failures | length) == 0 and (.tasks | length) == 1'
SOLVENTA_TASK=$(printf '%s\n' "$SOLVENTA_RESULT" | jq -er '.tasks[0].taskArn')
```

Debe haber una tarea y `failures` vacío. Si falla solamente la visualización del JSON, no volver a lanzar `run-task`: revisar primero la respuesta almacenada con `printf` porque la tarea podría haberse iniciado.

### 4. Esperar y verificar el resultado

```bash
aws ecs wait tasks-stopped \
  --region "$SOLVENTA_REGION" \
  --cluster "$SOLVENTA_CLUSTER" \
  --tasks "$SOLVENTA_TASK"

SOLVENTA_RESET_STATUS=$(aws ecs describe-tasks \
  --region "$SOLVENTA_REGION" \
  --cluster "$SOLVENTA_CLUSTER" \
  --tasks "$SOLVENTA_TASK" \
  --output json)

printf '%s\n' "$SOLVENTA_RESET_STATUS" | jq \
  '.tasks[0] | {stoppedReason, containers: [.containers[] | {name, exitCode, reason}]}'
printf '%s\n' "$SOLVENTA_RESET_STATUS" | jq -e \
  '(.failures | length) == 0 and any(.tasks[0].containers[]; .name == "seed" and .exitCode == 0)'
```

**Continuar únicamente si seed terminó con `exitCode: 0`.** Si el waiter vence, consultar la misma tarea antes de repetir el reset. Revisar los logs de esa ejecución exacta:

```bash
SOLVENTA_CLUSTER_NAME="${SOLVENTA_CLUSTER##*/}"
SOLVENTA_TASK_ID="${SOLVENTA_TASK##*/}"

aws logs tail "/ecs/$SOLVENTA_CLUSTER_NAME/catalogo" \
  --region "$SOLVENTA_REGION" \
  --log-stream-names "app/seed/$SOLVENTA_TASK_ID" \
  --since 15m \
  --format short
```

Si los logs aún no aparecen, esperar unos segundos y repetir solo la consulta de logs. Deben mostrar:

```text
experiment_quotes 0
experiment_projection 1000
experiment_catalog 1
RESET_OK
```

Para conservar la evidencia del reset:

```bash
SOLVENTA_RESET_EVIDENCE="experiments/exp-esc-01/results/resets/$(date -u +%Y%m%dT%H%M%SZ)-$SOLVENTA_TASK_ID"
mkdir -p "$SOLVENTA_RESET_EVIDENCE"
printf '%s\n' "$SOLVENTA_RESET_STATUS" > "$SOLVENTA_RESET_EVIDENCE/task.json"
```

## 3. Ejecutar las tres repeticiones

Después de completar los cuatro bloques de reset anteriores y confirmar salida 0 y `RESET_OK`, ejecutar **solo el comando de la repetición que corresponda**. La variable `SOLVENTA_TASK_ID` debe pertenecer al reset recién verificado. `--dataset-state` registra esa preparación; no ejecuta ni verifica SQL.

### Repetición 1: después del reset 1

```bash
python3 experiments/exp-esc-01/run.py \
  --mode autoscaling --series auto-002 --repetition 1 \
  --dataset-state "synthetic-v1; reset $SOLVENTA_TASK_ID confirmado: 0 cotizaciones, 1000 pólizas, 1 catálogo"
```

Esperar que termine, guardar evidencias y recolectar métricas con el comando de la sección 5. Volver a la sección 2, esperar el mínimo saludable y **ejecutar nuevamente los cuatro bloques de reset** antes de continuar.

### Repetición 2: después del reset 2

```bash
python3 experiments/exp-esc-01/run.py \
  --mode autoscaling --series auto-002 --repetition 2 \
  --dataset-state "synthetic-v1; reset $SOLVENTA_TASK_ID confirmado: 0 cotizaciones, 1000 pólizas, 1 catálogo"
```

Esperar que termine, conservar evidencias y recolectar métricas. Volver a la sección 2 y **ejecutar otro reset completo** después de recuperar el punto inicial.

### Repetición 3: después del reset 3

```bash
python3 experiments/exp-esc-01/run.py \
  --mode autoscaling --series auto-002 --repetition 3 \
  --dataset-state "synthetic-v1; reset $SOLVENTA_TASK_ID confirmado: 0 cotizaciones, 1000 pólizas, 1 catálogo"
```

Al finalizar, recolectar y consolidar. No resetear de nuevo salvo que vayas a iniciar otro ensayo. No ejecutar smoke ni POST manuales entre un reset y la carga: crearían cotizaciones y alterarían el punto inicial. El calentamiento sí genera datos y debe mantenerse igual en las tres repeticiones.

El reset iguala el contenido de las tablas; no vacía las cachés de PostgreSQL ni de las aplicaciones. No reconstruir imágenes entre repeticiones.

## 4. Perfil, protección y evidencias

`autoscaling-config.json` define:

| Parámetro | Valor |
| --- | --- |
| Calentamiento | 60 s a 500 RPM |
| Niveles | 500, 1.000, 2.000, 3.000, 5.000, 10.000, 25.000 y 50.000 RPM |
| Rampa por nivel | 300 s desde la tasa anterior |
| Meseta por nivel | 300 s |
| Pausa al terminar cada fase | 5 s para solicitudes pendientes |
| Timeout por POST | 2 s, sin reintentos |
| VUs preasignados / máximo | 2.000 / 2.000 |

La duración máxima aproximada es 82 min 25 s por repetición: unas 4 h 7 min de carga para la serie, más recuperación, resets y recolección. El generador usa tasas de llegada: intenta mantener las RPM aunque el servicio se ralentice. Verificar CPU, memoria y red del generador; 2.000 VUs no garantizan que el equipo produzca toda la carga.

Una meseta aprueba con p95 ≤ 250 ms, errores ≤ 1 %, cero iteraciones descartadas, volumen completo —se tolera una solicitud por discretización— y al menos 99 % del volumen esperado exitoso. Los errores incluyen timeouts, respuestas distintas de 201 y cuerpos incompatibles con el contrato sintético. `quotes_latency_ms` incluye conexión/TLS y solicitudes fallidas; `quotes_http_duration_ms` es una métrica adicional de diagnóstico.

Cada repetición se guarda en `results/auto-002/autoscaling/run-N/`:

| Archivo | Evidencia |
| --- | --- |
| `metadata.json` | Configuración, digests, hashes y nota del reset |
| `before.json`, `after.json` | Estado de servicios, tareas y destinos ALB |
| `execution.json` | Ventana UTC y código de salida k6 |
| `summary.json`, `console.log` | Resultados por meseta, métricas nativas y salida k6 |
| `scaling-timeline.jsonl` | Tareas desired/running/pending cada 15 s |
| `scaling-activities.json` | Actividades de Application Auto Scaling |
| `cloudwatch.json` | Métricas descargadas posteriormente con `collect.py` |

Las actividades AWS pueden incluir eventos anteriores; filtrarlas por la ventana de `execution.json`. Para seguir la primera ejecución desde otra terminal:

```bash
tail -f experiments/exp-esc-01/results/auto-002/autoscaling/run-1/console.log
```

Las carpetas existentes no se sobrescriben. Una salida no exitosa no elimina la evidencia ni inicia otra repetición. Si falla una consulta AWS, `unverified` significa que no se pudo comprobar el estado, no que desaparecieron servicios; revisar el error capturado. Si falla la precondición, k6 no comienza. Corregir la causa y usar otra serie cuando sea necesario repetir un número ya reservado.

## 5. Recolectar después de cada repetición y consolidar al final

Esperar unos minutos para la publicación de CloudWatch. Ejecutar después de cada repetición, antes de destruir recursos:

```bash
python3 experiments/exp-esc-01/collect.py experiments/exp-esc-01/results/auto-002
```

El recolector recorre las ejecuciones disponibles de la serie. Puede volver a ejecutarse y sobrescribe `cloudwatch.json`. Recoge CPU/memoria de servicios, CPU/conexiones/memoria de RDS y métricas del target group de cotización con resolución de 60 s. Una serie vacía no significa cero. Los resets posteriores no borran estas métricas históricas.

Después de las tres repeticiones:

```bash
python3 experiments/exp-esc-01/summarize.py experiments/exp-esc-01/results/auto-002
```

Genera **`report.md` y `autoscaling-report.json`**. También puede ejecutarse antes para ver un informe parcial, que indica repeticiones ausentes.

| Pregunta | Qué revisar |
| --- | --- |
| ¿Escaló al aumentar la carga? | Cambios de desired/running en la línea temporal y actividades AWS, correlacionados con CPU y fases k6 |
| ¿Cuánto tardó en agregar tareas? | Timestamps de actividades y muestras de tareas; la resolución del muestreo es 15 s |
| ¿Qué niveles cumplen el SLA? | Mesetas completas y aprobadas en cada repetición, p95 y errores; medianas de mesetas completas |
| ¿Se sostuvieron 50.000 RPM? | Las tres mesetas de esa tasa deben estar completas y aprobar; revisar cada resultado, no solo medianas |
| ¿Dónde se deterioró el servicio? | Resultados por fase, timeouts/HTTP en `summary.json`, CPU, dependencias y logs |
| ¿Se recuperó al retirar la carga? | Snapshot posterior y comprobaciones de la sección 2 antes del siguiente reset |

Las medianas del informe indican cuántas repeticiones completas las sustentan; no presentar una mediana de una sola como resultado de tres. `None` o una fase no alcanzada representan evidencia insuficiente, no capacidad cero. El máximo observado de tareas no prueba por sí solo que se cumplió el SLA. Este diseño no calcula una ganancia de capacidad entre configuraciones fijas de una y tres réplicas.

La política puede alcanzar su máximo y aun así saturarse. Revisar también el generador, RDS y los servicios que no escalan. La intermitencia de conectividad observada a baja carga puede afectar resultados; el informe no atribuye automáticamente todos los fallos a CPU o autoscaling.
