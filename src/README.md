# Servicios mínimos del experimento

Python 3.12, FastAPI, HTTPX y PostgreSQL con pool asíncrono. No hay cálculos de prima, validación aseguradora, suscripción ni integración con terceros reales. Las operaciones SQL y llamadas HTTP son reales; los resultados son sintéticos. Esto permite medir el montaje, sin garantizar de antemano sus umbrales ni extrapolarlos a la aplicación de negocio.

| Carpeta | Función y rutas |
| --- | --- |
| `cotizacion/` | `POST /cotizaciones` llama al catálogo, espera al simulador y persiste una cotización sintética. `GET /cotizaciones/{id}` permite comprobar que sobrevive al reemplazo de una tarea. |
| `consulta/` | `GET /consultas` devuelve `poliza-000001`; `GET /consultas/poliza-000042` consulta por clave primaria una póliza precargada. |
| `catalogo/` | `GET /catalogo` devuelve productos y reglas ficticias desde PostgreSQL. Incluye el comando `app.seed`. |
| `simulador/` | `GET /fuente` espera 50 ms mediante `asyncio.sleep`, sin bloquear otras solicitudes, y devuelve un valor fijo. |
| `common/` | Pool SQL, servidor, health check y logs; se copia dentro de cada imagen, no es otro servicio. |

Todos escuchan en `0.0.0.0:8080`, exponen `/health` y contienen el ejecutable `/app/healthcheck` requerido por ECS. API Gateway es administrado y no tiene carpeta de aplicación ni Dockerfile.

## Construcción

Desde la raíz del repositorio, el **contexto es `src/`**, porque contiene las dependencias y utilidades compartidas:

```
docker build --platform linux/amd64 -f src/cotizacion/Dockerfile -t solventa-cotizacion:exp1 src
docker build --platform linux/amd64 -f src/consulta/Dockerfile -t solventa-consulta:exp1 src
docker build --platform linux/amd64 -f src/catalogo/Dockerfile -t solventa-catalogo:exp1 src
docker build --platform linux/amd64 -f src/simulador/Dockerfile -t solventa-simulador:exp1 src
```

Cada imagen corre con usuario no root. Las dependencias directas tienen versiones fijas; los tags base y las dependencias transitivas pueden variar entre reconstrucciones. Publicar una vez y reutilizar los mismos digests ECR durante las comparaciones, conforme al Terraform.

## Arranque local opcional

```
docker compose -f src/compose.yaml up --build -d
```

Compose inicia PostgreSQL, ejecuta la carga sintética y espera los health checks antes de iniciar cotización. Solo expone cotización y consulta en localhost. Las credenciales de Compose son exclusivamente locales; AWS usa Secrets Manager y TLS. No usar esta base local para afirmar resultados del montaje AWS.

```
curl -i http://localhost:8081/cotizaciones \
  -H 'Content-Type: application/json' \
  -H 'X-Correlation-Id: ejemplo-001' \
  -d '{"product_id":"producto-sintetico"}'
curl -i http://localhost:8082/consultas/poliza-000001
```

Una cotización exitosa devuelve **201** con un UUID; la consulta devuelve **200**. Se puede consultar ese UUID en `/cotizaciones/{id}`. Las pólizas válidas van de `poliza-000001` a `poliza-001000`. Un identificador desconocido devuelve 404 y una dependencia no disponible devuelve 503. Las entradas mal formadas devuelven 422.

```
docker compose -f src/compose.yaml down
```

Esto conserva el volumen. La carga inicial es idempotente y no borra cotizaciones existentes.

## Uso con Terraform

1. Construir/publicar las cuatro imágenes en los repositorios del output `ecr_repositories` de `infra/base` y copiar los digests a `image_digests`.
2. En `infra/services`, proporcionar los cuatro `image_digests` y configurar `seed_command=["python", "-m", "app.seed", "--dataset", "synthetic-v1"]`.
3. Después de aprovisionar, ejecutar explícitamente la tarea de `seed_task` mediante ECS RunTask, con los parámetros de red del output de `infra/services`, Fargate e IP pública habilitada. Terraform solo crea la definición y no ejecuta la carga.
4. Esperar a que la tarea seed termine con código 0 y los servicios estén saludables. Antes de cargar las tablas, sus health checks devuelven 503 y ECS puede reemplazar tareas; no empezar las mediciones hasta terminar la preparación.
5. Usar `entry_url/cotizaciones` y `entry_url/consultas/poliza-000001`. API Gateway establece el identificador de correlación y las aplicaciones lo propagan.

El usuario SQL de la carga debe poder crear tablas. `app.seed` usa una única transacción con bloqueo asesor para tolerar ejecuciones concurrentes y crea catálogo, 1.000 pólizas e infraestructura de persistencia de cotizaciones. No genera datos personales.

## Condiciones controladas

- `DB_POOL_SIZE=5`, `DB_SSLMODE=require` en AWS. No se retienen conexiones SQL durante la espera del simulador.
- `RESPONSE_DELAY_MS=50` es una espera configurada, no una promesa de latencia total de 50 ms. `FAILURE_RATE=0` mantiene la fuente estable; admite valores de 0 a 1 para usos posteriores.
- `EXTERNAL_SOURCE_TIMEOUT_MS=150`, sin reintentos de aplicación. Un timeout se refleja como error 503 y no como éxito artificial.
- `RULES_CACHE_ENABLED=true` conserva únicamente el catálogo inmutable `synthetic-v1` por proceso. El health check de cotización lo precarga antes de recibir tráfico del ALB; los resultados transaccionales siempre van a PostgreSQL.
- Logs JSON por solicitud: correlación, estado, duración total y duración por dependencia. No se registran contraseñas ni cuerpos. Los mensajes de arranque del servidor y librerías pueden tener formato de texto.
- Una instancia de Uvicorn por tarea y cierre ordenado de 20 s, dentro de los 30 s de ECS. No se conserva sesión local.
- El volumen de cotizaciones crece durante las pruebas. Registrar el estado inicial de la base y preparar el mismo estado entre comparaciones; `seed` no reinicia los resultados anteriores.

La prueba de disponibilidad debe detener una tarea cuando haya dos réplicas saludables. El código no detiene tareas ni ejecuta carga automáticamente. Los p95, capacidad y recuperación deben medirse; este prototipo evalúa infraestructura y acceso técnico, no el costo de reglas de negocio reales.
