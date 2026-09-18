# Informe de hallazgos — EXP-DIS-01

**Estado:** hipótesis confirmada.
**Fecha de ejecución:** 18 de septiembre de 2026.
**Serie válida:** `dis-002` (tres repeticiones).

## 1. Ficha del experimento

| Campo | Descripción |
| --- | --- |
| Título | EXP-DIS-01 — Disponibilidad ante detención de una tarea ECS de cotización |
| Propósito | Verificar que, con dos tareas Fargate activas en cotización, la detención abrupta de una de ellas no interrumpe el servicio y que ECS restablece dos destinos sanos dentro de una ventana acotada. |
| Resultados esperados | Con 150 solicitudes/minuto sostenidas (180 s de línea base + 180 s de perturbación): éxito ≥99 %, p95 de perturbación ≤500 ms y RTO ≤120 s, en tres repeticiones completas. |
| Recursos requeridos | API Gateway, ALB, ECS/Fargate, RDS PostgreSQL, Application Auto Scaling, CloudWatch, AWS CLI, k6, tarea ECS `seed` y dataset sintético. |
| Elementos de arquitectura involucrados | API Gateway → ALB → `cotizacion` (2 tareas); `cotizacion` → `catalogo` + `simulador`; RDS PostgreSQL Single-AZ; Service Connect y CloudWatch. |
| Configuración controlada | `cotizacion` fijo en 2 tareas (min=max=2); `consulta`/`catalogo`/`simulador` fijos en 1; sin políticas de autoscaling en ningún servicio; simulador fijo en 50 ms, sin fallos ni reintentos. |
| Esfuerzo incremental estimado | ~2 horas: preparación de escalado, cuatro resets, tres corridas de 6 min con inyección de falla, recolección CloudWatch y consolidación. |

## 2. Hipótesis de diseño

| Elemento | Definición |
| --- | --- |
| Hipótesis | Con dos tareas de cotización y 150 RPM sostenidas, detener una tarea a mitad de carga no degrada el éxito por debajo de 99 % ni el p95 por encima de 500 ms durante la perturbación, y ECS repone la segunda tarea (`desired=2`, `running=2`, dos destinos `healthy`) en ≤120 s. |
| Punto de sensibilidad | La recuperación depende del ciclo de vida de ECS (`stopTask` → nueva tarea `PROVISIONING`→`RUNNING` → health check ALB cada 5 s con umbral 2). El tráfico en curso depende de que el ALB retire el destino caído y balancee sobre el sobreviviente sin que la cola de solicitudes se degrade. |
| Historia de arquitectura asociada | **HA-DIS-01 — Redundancia activa-activa sin autoscaling reactivo:** dos tareas de cotización tras el mismo target group, sin depender de una política de escalado para tolerar la falla (el segundo reemplazo llega por reposición de `desiredCount`, no por scale-out); health checks agresivos (intervalo 5 s, umbral 2) aceleran la detección y el registro del reemplazo. |
| Nivel de incertidumbre | Bajo para este nivel de carga y este tipo de falla (`stop-task` único). Medio para fallas simultáneas de más de una tarea, saturación de capacidad durante la reposición, o un Single-AZ de RDS con degradación concurrente, que no fueron parte de este experimento. |

## 3. Resultados por repetición

Las tres repeticiones de `dis-002` completaron con `exit_code=0` y RTO medido.

| Corrida | Éxito perturbación | p95 perturbación (ms) | Error | RTO (s) | Aprobada |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 100 % | 176.5 | 0 % | 61.32 | Sí |
| 2 | 100 % | 178.0 | 0 % | 78.37 | Sí |
| 3 | 100 % | 258.5 | 0 % | 92.02 | Sí |

Medianas: éxito=100 %, p95=178.0 ms, RTO=78.37 s. Los tres RTO están por debajo del límite de 120 s con margen (27–49 s).

La fase de línea base (sin perturbación) también se mantuvo estable en las tres corridas: 100 % de éxito y p95 entre 194 y 225 ms, confirmando que la carga base no era en sí misma un factor limitante.

### ¿Se confirmó la hipótesis de diseño?

Sí. Las tres corridas fueron completas (`valid_load=true`), no hubo solicitudes descartadas (`dropped_iterations=0`) y los tres pares (éxito/p95, RTO) cumplieron sus umbrales. No se registró ningún error HTTP durante la perturbación en ninguna repetición.

### Decisiones de arquitectura que favorecieron el resultado

- Mantener dos tareas activas en `cotizacion` evita que la caída de una interrumpa el servicio: el ALB balancea de inmediato sobre la tarea sobreviviente.
- Los health checks agresivos del ALB (intervalo 5 s, umbral sano/no sano 2, deregistro 5 s) aceleran tanto la detección de la tarea caída como el registro del reemplazo.
- Fijar `desiredCount=2` sin depender de una política de autoscaling evita la latencia adicional de una decisión de escalado: ECS repone la tarea por mantenimiento de `desiredCount`, no por scale-out reactivo.
- El simulador estable a 50 ms y la caché de reglas mantienen acotada la latencia de cotización incluso mientras el clúster opera con una sola tarea sana durante la ventana de recuperación.

### ¿Por qué no se evaluaron escenarios más severos y qué cambiaría?

Solo se probó la pérdida de una tarea sobre un total de dos, con un único punto de falla por corrida. No se evaluó: pérdida simultánea de ambas tareas de cotización, fallas concurrentes en `catalogo`/`simulador`/`consulta` (puntos únicos de falla sin redundancia), degradación de RDS Single-AZ, ni carga sostenida durante la reposición (la carga se mantuvo constante en 150 RPM, no se incrementó durante la ventana de recuperación).

Si una prueba posterior de mayor severidad no cumple el RTO o el éxito esperado, medir primero el tiempo de `PROVISIONING`→`RUNNING` de la tarea de reemplazo, el tiempo hasta el primer health check exitoso, y la contención de conexiones SQL con una sola tarea sana. Alternativas según la evidencia: reducir el intervalo o el umbral de health check, añadir una tercera tarea de reserva (N+2), o introducir autoscaling reactivo como respaldo de la redundancia fija.

## 4. Evidencia

- Resumen consolidado: `experiments/exp-dis-01/results/dis-002/report.md` y `report.json`.
- Resultados por corrida: `results/dis-002/run-{1,2,3}/summary.json`, `execution.json`, `timeline.json`, `stop-task.json`, `before.json`, `after.json`, `cloudwatch.json`, `logs.json`.
- Endpoint medido: `https://ox05ty0z5g.execute-api.us-east-1.amazonaws.com`.
- Clúster: `solventa-exp`; target group de cotización con dos destinos `healthy` antes y después de cada corrida.
- Reset del dataset sintético confirmado antes de cada repetición (`experiment_quotes`=0, `experiment_projection`=1000, `experiment_catalog`=1); evidencia en `experiments/exp-esc-01/results/resets/`.
- RDS verificada: PostgreSQL 16.13, `db.t4g.micro`, Single-AZ.
- `git_commit` registrado en la corrida: `c200bbe`. `k6 v2.2.0`.

### Notas técnicas sobre la ejecución

- **Sin Terraform local:** el estado de Terraform de `infra/services` reside en otra máquina (`terraform output` devuelve `{}` en este entorno). `run.py` se adaptó para descubrir la configuración (cluster, ARNs de task definitions, target groups, ALB, variables de entorno del simulador/cotización) directamente contra AWS en vivo, en vez de leer `terraform output -json`. El escalado a `cotizacion=2` y el registro de los scalable targets se hizo con AWS CLI directo, según lo indicado en `HANDOFF.md`.
- **Serie `dis-001` descartada:** la primera corrida (repetición 1) se ejecutó con una versión de `availability.js` en la que k6 2.x no generaba las submétricas `quotes_completed{scenario:...}` ni ninguna submétrica de la fase `baseline`, porque k6 solo calcula una submétrica por etiqueta cuando existe un *threshold* que la referencia explícitamente (comportamiento distinto al bug de conteo de `exp-lat-01`, pero de la misma familia). Se corrigió `availability.js` añadiendo *thresholds* triviales (`count>=0`) para forzar la creación de esas submétricas en ambas fases, y se verificó el comportamiento con una prueba local aislada de k6 antes de aplicar el cambio. Por cambiar el `script_sha256`, `run.py` exige una serie nueva para preservar comparabilidad; `dis-001/run-1` se conserva como evidencia técnica no válida (el p95 y el RTO de esa corrida sí eran correctos — 151 ms y 86.8 s — pero el conteo de solicitudes completadas no era fiable) y no se mezcló con `dis-002`.
- **Bug de `collect.py` corregido:** una indentación incorrecta hacía que solo se guardara la última de las ~17 métricas de CloudWatch por corrida. Se corrigió antes de recolectar la evidencia de `dis-002`; las tres corridas tienen ahora las 17 métricas completas sin errores de recolección.
- **Estado de AWS al finalizar:** `cotizacion` quedó con `desiredCount=2` (fijo, sin autoscaling) y los cuatro servicios tienen scalable targets registrados con min=max=capacidad fija y sin políticas de escalado activas, tal como exige el escenario DIS. No se revirtió el entorno a la configuración previa (`cotizacion=1`, escenario LAT) porque el handoff no lo solicitó; queda pendiente decidir si se revierte antes de dejar el ambiente en reposo.
