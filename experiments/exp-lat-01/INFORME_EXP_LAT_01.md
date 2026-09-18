# Informe de hallazgos — EXP-LAT-01

**Estado:** hipótesis confirmada.
**Fecha de ejecución:** 18 de septiembre de 2026.
**Serie válida:** `lat-003` (tres repeticiones, evidencia completa).

## 1. Ficha del experimento

| Campo | Descripción |
| --- | --- |
| Título | EXP-LAT-01 — Latencia de cotización y consulta de póliza |
| Propósito | Verificar la latencia extremo a extremo y la tasa de errores de los dos recorridos públicos bajo carga base sostenida. |
| Resultados esperados | A 500 solicitudes/minuto por endpoint durante 10 min: cotización p95 ≤250 ms, consulta p95 ≤150 ms y errores técnicos ≤1%, en tres repeticiones. |
| Recursos requeridos | API Gateway, ALB, ECS/Fargate, RDS PostgreSQL, ECR, CloudWatch, AWS CLI, k6, tarea ECS `seed` y dataset sintético. |
| Elementos de arquitectura involucrados | API Gateway → ALB → `cotizacion`/`consulta`; `cotizacion` → `catalogo` + `simulador`; RDS PostgreSQL Single-AZ; Service Connect y CloudWatch. |
| Configuración controlada | Una tarea saludable por servicio; sin políticas CPU de autoscaling; simulador fijo en 50 ms, sin fallos ni reintentos. |
| Esfuerzo incremental estimado | ~1.5 horas: preparación, tres resets, tres cargas de 10 min, recolección CloudWatch, consolidación. |

## 2. Hipótesis de diseño

| Elemento | Definición |
| --- | --- |
| Hipótesis | Con una tarea fija por servicio y 500 RPM simultáneas por endpoint, la cotización mantiene p95 ≤250 ms y la consulta p95 ≤150 ms, con errores ≤1%. |
| Punto de sensibilidad | La cotización depende del simulador (50 ms), catálogo/reglas, escritura en RDS, pool SQL y serialización. La consulta depende principalmente de la lectura indexada de la proyección en RDS. |
| Historia de arquitectura asociada | **HA-LAT-01 — Recorridos desacoplados con dependencias controladas:** API Gateway y ALB enrutan a servicios de dominio independientes; la cotización evita retener una conexión SQL mientras espera el simulador y usa caché de reglas; la consulta lee una proyección sintética por clave primaria. |
| Nivel de incertidumbre | Bajo para el nivel probado: tres corridas completas y comparables, con precondiciones verificadas antes y después de cada una. Medio para cargas superiores, fallos de dependencia, cold cache, escalamiento o una base Multi-AZ, que no fueron parte de este experimento. |

## 3. Resultados por nivel de carga

Solo se evaluó un nivel: **500 RPM por endpoint durante 10 minutos**, equivalentes a 1.000 RPM agregadas sobre API Gateway. No es una rampa de escalabilidad.

| Endpoint | p95 por corrida (ms) | p95 mediano (ms) | Error por corrida | Solicitudes completadas | Resultado |
| --- | --- | ---: | --- | --- | --- |
| Cotización | 159 / 158 / 154 | **158** | 0% / 0% / 0% | 5.001 / 5.001 / 5.000 | Cumple ≤250 ms y ≤1% |
| Consulta | 101 / 92 / 91 | **92** | 0% / 0% / 0% | 5.001 / 5.000 / 5.001 | Cumple ≤150 ms y ≤1% |

### ¿Se confirmó la hipótesis de diseño?

Sí. Las tres corridas fueron completas (`valid_load=true`), no hubo iteraciones descartadas y ambos endpoints cumplieron sus umbrales con margen amplio: cotización a un 37% del límite (158 ms de 250 ms) y consulta a un 61% del límite (92 ms de 150 ms). No se registró ningún error técnico en ninguna de las seis mediciones (3 corridas × 2 endpoints).

### Decisiones de arquitectura que favorecieron el resultado

- Separar cotización y consulta evita que la lectura de pólizas compita directamente con la lógica de cotización.
- El simulador estable a 50 ms, sin reintentos, mantiene controlada la dependencia externa.
- La caché de reglas reduce llamadas repetidas a catálogo en cotización.
- La cotización no retiene la conexión PostgreSQL mientras espera la fuente externa.
- Las proyecciones sintéticas de consulta se resuelven por clave primaria.
- API Gateway, ALB y una tarea saludable por servicio permanecieron estables; no hubo escalamiento durante las mediciones (confirmado por los snapshots `before.json`/`after.json` de las tres corridas).

### ¿Por qué falló en niveles altos y qué cambiaría?

No se probaron niveles altos; por tanto, no hubo un fallo de capacidad atribuible en EXP-LAT-01. No debe interpretarse este resultado como evidencia de capacidad superior a 500 RPM por endpoint.

Si una prueba posterior falla a mayor carga, se debe medir primero CPU/memoria de cada servicio, conexiones y latencia de RDS, tiempo de respuesta del simulador, aciertos de caché y latencia API Gateway/ALB. Las alternativas de cambio, según la evidencia, son: habilitar autoscaling con límites y política validados, aumentar capacidad/pool de conexiones, optimizar índices y consultas de RDS, ampliar caché de reglas o escalar catálogo/simulador como dependencias compartidas.

## 4. Evidencia

- Resumen consolidado: `experiments/exp-lat-01/results/lat-003/report.md` y `report.json`.
- Resultados por corrida: `results/lat-003/run-{1,2,3}/summary.json`, `metadata.json`, `execution.json`, `before.json`, `after.json`, `console.log`, `cloudwatch.json` (17 métricas por corrida, sin errores de recolección), `logs.json`.
- Endpoint medido: `https://ox05ty0z5g.execute-api.us-east-1.amazonaws.com`.
- Clúster: `solventa-exp`; `before.json`/`after.json` de las tres corridas confirman una tarea sana por servicio, digests correctos y ambos target groups saludables, antes y después de cada medición.
- RDS verificada: PostgreSQL 16.13, `db.t4g.micro`, Single-AZ.
- Reset del dataset sintético confirmado antes de cada repetición (`experiment_quotes`=0, `experiment_projection`=1000, `experiment_catalog`=1); evidencia en `experiments/exp-esc-01/results/resets/`.
- `git_commit` registrado en la corrida: `c200bbe`. `k6 v2.2.0`.

### Notas técnicas sobre la ejecución de `lat-003`

- **Sin Terraform local:** al igual que en EXP-DIS-01, el estado de Terraform de `infra/services` reside en otra máquina (`terraform output` devuelve `{}` en este entorno). Se adaptó `run.py` para descubrir toda la configuración (cluster, task definitions, digests de imagen, target groups, variables de entorno del simulador/cotización, grupos de logs) directamente contra AWS en vivo, sin cambiar la lógica de validación de precondiciones ni de comparabilidad entre corridas.
- **Ambiente revertido antes de medir:** entre EXP-DIS-01 y esta serie, `cotizacion` había quedado fijo en 2 tareas. Se revirtió a 1 tarea (`desiredCount=1`, scalable target min=max=1) y se confirmó un único destino `healthy` por target group antes de iniciar `lat-003`.
- **Serie `lat-002` superada, no descartada:** la serie anterior (`lat-002`) se generó sin pasar por `run.py` — cada `run-N/` solo tenía `summary.json` y `console.log` vacío, sin `metadata.json`, `execution.json`, snapshots `before/after` ni `cloudwatch.json`. Las cifras de `lat-002` (cotización p95 mediano 151 ms, consulta 97 ms) son consistentes con las de `lat-003` (158 ms y 92 ms respectivamente), lo que sugiere que las mediciones originales eran confiables a pesar del hueco de evidencia. `lat-003` es ahora la serie autoritativa por tener el rastro de evidencia completo y verificable; `lat-002` se conserva como referencia histórica en `results/lat-002/`.
- **Serie `lat-001` inválida:** se mantiene como antes — el script k6 inicial no leía correctamente los contadores bajo k6 2.x; no se mezcló con ninguna serie aprobada.
