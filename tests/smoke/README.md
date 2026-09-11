# Pruebas funcionales antes de la carga

Ejecutar desde la raíz del repositorio. Python 3.10+ sin dependencias externas; AWS CLI y Terraform para leer el despliegue. La suite hace solicitudes secuenciales y crea **tres cotizaciones sintéticas**, que conserva para comprobar persistencia. No borra datos, ejecuta seed, escala servicios, cambia reglas de red ni detiene tareas.

## Suite completa AWS + HTTP

Con un perfil AWS válido de la cuenta desplegada:

```bash
export AWS_PROFILE=solventa
aws sso login --profile "$AWS_PROFILE"
aws sts get-caller-identity
python3 tests/smoke/run.py
```

Si el perfil no utiliza SSO, omitir `aws sso login` y usar su mecanismo de autenticación. La suite lee la URL, región, clúster, réplicas y digests desde `infra/services/terraform.tfstate` mediante `terraform output`.

La identidad necesita `ecs:DescribeServices`, `ecs:ListTasks`, `ecs:DescribeTasks`, `elasticloadbalancing:DescribeTargetHealth` y `logs:FilterLogEvents` sobre los recursos correspondientes. No necesita leer contraseñas de Secrets Manager.

## Qué se comprueba

| Componente | Comprobaciones |
| --- | --- |
| Los cuatro servicios ECS | Número de tareas, despliegue estable, health checks saludables y digests/revisiones iguales al estado Terraform. |
| ALB | Destinos saludables de consulta y cotización. |
| Consulta | Ruta por defecto y pólizas 1, 42 y 1.000; proyección exacta, versión sintética y cabecera de correlación. |
| Cotización | Tres POST con IDs UUID diferentes, respuesta sintética y lectura GET posterior idéntica al resultado persistido. También prueba el producto por defecto con `{}`. |
| Catálogo | Salud de su contenedor —su health check lee PostgreSQL— y versión `synthetic-v1` usada en cotización. |
| Simulador | Respuesta integrada correcta, configuración de 50 ms y logs que acreditan la espera, propagando la correlación del POST. |
| Errores esperados | 404 para IDs desconocidos y rutas no publicadas; 422 para producto vacío o demasiado largo; 405 para GET en la colección de cotizaciones. |
| Observabilidad | Mismo ID de correlación en cotización y simulador, estado exitoso y tiempos de PostgreSQL/simulador. |

Los logs pueden tardar en llegar: por defecto espera hasta 60 segundos; ampliar con `--log-wait-seconds 120`. Esa espera no agrega tráfico HTTP. Si no se encuentran logs, la comprobación falla; no los trata como evidencia positiva.

## Solo HTTP

Sin credenciales AWS, usando la URL del estado local:

```bash
python3 tests/smoke/run.py --http-only
```

Sin estado Terraform, indicar la URL de API Gateway:

```bash
python3 tests/smoke/run.py --http-only \
  --base-url https://ID.execute-api.us-east-1.amazonaws.com
```

Este modo comprueba los recorridos públicos y la integración, pero no certifica ECS ni CloudWatch. Catálogo y simulador no se publican mediante API Gateway: no abrir sus grupos de seguridad solo para estas pruebas.

Si se ejecuta desde un entorno que ya tiene acceso a los endpoints internos, se pueden agregar `--catalog-url http://catalogo:8080` y `--simulator-url http://simulador:8080`. Service Connect solo resuelve esos nombres dentro de las tareas configuradas; no son DNS públicos para el portátil. Estas opciones añaden pruebas directas de `/health`, `/catalogo` y `/fuente`.

## Evidencias y criterio para continuar

Cada ejecución crea `tests/smoke/results/<fecha UTC>/report.json` con PASS/FAIL, latencias observadas, IDs de cotización, correlaciones y estado de tareas. La suite completa añade `correlated-logs.json`. Los resultados están ignorados por Git.

- Código de salida 0: todas las comprobaciones del modo elegido pasaron.
- Código 1: existe algún fallo; resolverlo antes de ejecutar k6.
- Una excepción al cargar estado/credenciales es un error de preparación, no un resultado funcional.

Un 503 con `Dependency unavailable` exige revisar los logs del servicio para distinguir PostgreSQL, pool, catálogo o simulador. El resultado no identifica por sí solo cuál dependencia falló. Los logs de la aplicación exponen `error_type` sin revelar secretos.

La suite no mide capacidad ni certifica p95 de carga. Las tres lecturas de cotización comprueban persistencia a través de la API; no demuestran recuperación tras detener una tarea. El catálogo puede estar en caché en cotización: para acreditar la lectura actual de PostgreSQL se usa la salud ECS de catálogo o su endpoint directo. No se simulan caídas de dependencias en esta preparación.
