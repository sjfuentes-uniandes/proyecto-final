# Proyecto final — Solventa

Prototipo para los experimentos de escalabilidad, disponibilidad y latencia. Incluye infraestructura Terraform en [`infra/`](infra/README.md), cuatro servicios sintéticos con Docker en [`src/`](src/README.md) y diagramas en `docs/diagramas`.

## Levantar el ambiente en AWS

Esta guía describe comandos para ejecutar manualmente. Crear la documentación no ejecuta el despliegue. El flujo tiene dos raíces Terraform y estados independientes: primero `infra/base`, después publicar las imágenes y desplegar `infra/services`. No ejecutar Terraform desde `infra/` directamente. Si ya existe un despliegue de la estructura anterior, consultar [la migración de estado](infra/README.md#migración-desde-la-estructura-anterior) antes de continuar.

```text
Cliente → API Gateway administrado (HTTPS) → ALB público (HTTP)
                                             ├─ /cotizaciones → cotizacion
                                             │                   ├─ catalogo
                                             │                   └─ simulador (50 ms)
                                             └─ /consultas → consulta

cotizacion / catalogo / consulta → RDS PostgreSQL Single-AZ
Tareas Fargate con IP pública → Internet Gateway → ECR, secretos y logs
```

El montaje utiliza una zona para las tareas y RDS, y subredes en dos zonas para el ALB. No crea NAT Gateway ni EIP. Las IP públicas, ALB, Fargate, API Gateway y RDS generan costos; el despliegue `infra/base` también crea recursos de pago. La entrada está habilitada sin autenticación para datos sintéticos y el ALB admite acceso directo; medir siempre a través de API Gateway.

Atajos de `make` que envuelven los mismos comandos de esta guía (requieren las credenciales y herramientas de la sección 1-2):

| Comando | Equivale a |
| --- | --- |
| `make deploy` | Secciones 4-7: `infra/base` (init/apply), build+push de las cuatro imágenes con digests, `infra/services` (init/apply) y el seed inicial. No incluye espera de servicios ni smoke. |
| `make experiment-clean-up` | Reset transaccional de la BD antes de cada repetición de EXP-ESC-01 ([guía completa](experiments/exp-esc-01/README.md#2-recuperar-el-punto-inicial-antes-de-cada-reset)). |
| `make destroy` | Sección 12, en orden inverso: destruye `infra/services` y luego `infra/base` (los repositorios ECR usan `force_delete`, no requieren vaciarse a mano). |

`make deploy` y `make destroy` no piden ninguna confirmación propia: cada `terraform apply` muestra su plan y hace la única pregunta del script, la de Terraform ("Do you want to perform these actions?" / para destruir). `SOLVENTA_YES=1` omite esas preguntas para ejecución no interactiva.

### 1. Requisitos

Instalar en el equipo:

- Git.
- Terraform **1.9 o superior, menor que 2.0**.
- AWS CLI v2.
- Docker con el motor en ejecución y soporte Buildx; Docker Desktop lo incluye.
- Bash, `jq` y `curl`.

La identidad AWS debe poder administrar VPC/subredes/grupos de seguridad, balanceadores, API Gateway, ECS, ECR, RDS, Cloud Map, IAM, CloudWatch y EventBridge. También necesita publicar imágenes, ejecutar/describir tareas ECS y `iam:PassRole` sobre los roles de ejecución y tarea creados por Terraform. En cuentas nuevas puede requerirse crear roles vinculados a servicios. Secrets Manager se usa para la contraseña administrada de RDS; no es necesario copiarla a archivos locales.

Verificar las cuotas de Fargate On-Demand: con la configuración base las cuatro tareas requieren al menos **2 vCPU**; con tres réplicas de cotización requieren **3 vCPU**, más capacidad temporal para despliegues y la tarea seed. Verificar también las cuotas de API Gateway para el objetivo de 50.000 solicitudes/minuto.

Todos los comandos siguientes se ejecutan desde la **raíz de este repositorio**, en una misma sesión Bash. Si usas Zsh, abre primero `bash`. Detente ante cualquier comando fallido; no continúes con variables vacías.

```bash
set -euo pipefail
terraform version
aws --version
docker info
docker buildx version
jq --version
```

### 2. Autenticarse y seleccionar cuenta/región

Si la organización usa IAM Identity Center, configurar el perfil una vez e iniciar sesión:

```bash
aws configure sso --profile solventa
aws sso login --profile solventa
```

Si ya tienes otro perfil válido, utiliza su nombre en `AWS_PROFILE` y omite la configuración SSO. Los perfiles con credenciales temporales también son válidos; no guardar claves en Terraform ni en el repositorio. [Guía oficial de autenticación SSO](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html).

```bash
export AWS_PROFILE=solventa
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION="$AWS_REGION"
export AWS_PAGER=""
aws sts get-caller-identity
```

Comprueba que `Account` y `Arn` correspondan a la cuenta e identidad esperadas. La región de `terraform.tfvars` debe coincidir con `AWS_REGION`; el proveedor usa explícitamente la variable Terraform `aws_region`.

### 3. Configurar e inicializar Terraform

Crear el archivo personal solo si todavía no existe:

```bash
if [ ! -f infra/base/terraform.tfvars ]; then
  cp infra/base/terraform.tfvars.example infra/base/terraform.tfvars
fi
```

Editar `infra/base/terraform.tfvars` y conservar inicialmente:

```hcl
aws_region        = "us-east-1"
name              = "solventa-exp"
```

Mantener los demás valores del ejemplo. `name` identifica el clúster, la base y los repositorios; utilizar un nombre propio si otra persona ya desplegó el montaje en la misma cuenta/región. No cambiarlo entre fases.

```bash
terraform -chdir=infra/base init -input=false
terraform -chdir=infra/base fmt -check
terraform -chdir=infra/base validate
```

Cada estado es **local** (`infra/base/terraform.tfstate` y `infra/services/terraform.tfstate`). Está excluido de Git, junto con archivos personales, planes y `.terraform/`. Conservarlo para poder actualizar y eliminar el ambiente. Versionar el `.terraform.lock.hcl` de cada raíz. Para operar entre varias personas, acordar un backend compartido antes de desplegar; no ejecutar desde estados locales independientes contra el mismo ambiente.

### 4. Crear la infraestructura base

```bash
terraform -chdir=infra/base plan -out=base.tfplan
terraform -chdir=infra/base apply base.tfplan
terraform -chdir=infra/base output -json ecr_repositories
```

Revisar el plan antes de ejecutar `apply`: aplicar un plan guardado no pide otra confirmación. Se crean red, RDS, ALB con listener sin destinos, ECR, clúster vacío, namespace Service Connect y eventos ECS. API Gateway, tareas y roles de aplicación se crean en services. RDS puede tardar varios minutos. Todavía no hay tareas de aplicación ni datos; el endpoint no está listo para usarse.

Guardar los datos necesarios para los siguientes pasos en variables de esta sesión:

```bash
SOLVENTA_REPOSITORIES=$(terraform -chdir=infra/base output -json ecr_repositories)
SOLVENTA_CONFIGURATION=$(terraform -chdir=infra/base output -json foundation)
SOLVENTA_CLUSTER=$(jq -er '.cluster.name' <<< "$SOLVENTA_CONFIGURATION")
SOLVENTA_DEPLOY_REGION=$(jq -er '.region' <<< "$SOLVENTA_CONFIGURATION")
test "$AWS_REGION" = "$SOLVENTA_DEPLOY_REGION"
SOLVENTA_REGISTRY=$(jq -er '.catalogo | split("/")[0]' <<< "$SOLVENTA_REPOSITORIES")
```

### 5. Construir y publicar las cuatro imágenes en ECR

Autenticar Docker en el registro de este despliegue:

```bash
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$SOLVENTA_REGISTRY"
```

Publicar una versión identificable. Cada servicio tiene Dockerfile propio, pero todos necesitan **`src/` como contexto**, porque copian el código común y las dependencias. `linux/amd64` coincide con las tareas ECS incluso si construyes desde un Mac Apple Silicon.

```bash
SOLVENTA_IMAGE_TAG="exp-$(date -u +%Y%m%dT%H%M%SZ)"
for SOLVENTA_SERVICE in catalogo simulador consulta cotizacion; do
  SOLVENTA_REPOSITORY=$(jq -er --arg service "$SOLVENTA_SERVICE" '.[$service]' <<< "$SOLVENTA_REPOSITORIES")
  docker buildx build \
    --platform linux/amd64 \
    --provenance=false \
    --file "src/$SOLVENTA_SERVICE/Dockerfile" \
    --tag "$SOLVENTA_REPOSITORY:$SOLVENTA_IMAGE_TAG" \
    --push src
done
```

ECR tiene tags inmutables. Para otra publicación, generar otro tag; no sobrescribir el existente. Mantener los mismos digests entre escenarios del experimento. [Publicación de imágenes en ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/getting-started-cli.html).

Obtener los digests reales y generar el archivo que Terraform carga automáticamente:

```bash
SOLVENTA_DIGESTS='{}'
for SOLVENTA_SERVICE in catalogo simulador consulta cotizacion; do
  SOLVENTA_REPOSITORY=$(jq -er --arg service "$SOLVENTA_SERVICE" '.[$service]' <<< "$SOLVENTA_REPOSITORIES")
  SOLVENTA_REPOSITORY_NAME=${SOLVENTA_REPOSITORY#*/}
  SOLVENTA_DIGEST=$(aws ecr describe-images \
    --repository-name "$SOLVENTA_REPOSITORY_NAME" \
    --image-ids "imageTag=$SOLVENTA_IMAGE_TAG" \
    --query 'imageDetails[0].imageDigest' --output text)
  SOLVENTA_DIGESTS=$(jq --arg service "$SOLVENTA_SERVICE" --arg digest "$SOLVENTA_DIGEST" \
    '. + {($service): $digest}' <<< "$SOLVENTA_DIGESTS")
done
jq -n --argjson digests "$SOLVENTA_DIGESTS" '{image_digests: $digests}' \
  > infra/services/images.auto.tfvars.json
cat infra/services/images.auto.tfvars.json
```

Cada valor debe comenzar con `sha256:` y contener 64 caracteres hexadecimales. El archivo está ignorado por Git; conservar una copia junto con la evidencia del experimento. No mantener otro `image_digests` contradictorio en `terraform.tfvars`.

### 6. Habilitar las aplicaciones y la definición de carga

Crear la configuración independiente de los servicios:

```bash
if [ ! -f infra/services/terraform.tfvars ]; then
  cp infra/services/terraform.tfvars.example infra/services/terraform.tfvars
fi
terraform -chdir=infra/services init -input=false
```

Editar `infra/services/terraform.tfvars`. No contiene región ni nombre: los hereda de la base. Conservar:

```hcl
quotation_replicas = 1
seed_command    = ["python", "-m", "app.seed", "--dataset", "synthetic-v1"]
```

```bash
terraform -chdir=infra/services plan -out=services.tfplan
terraform -chdir=infra/services apply services.tfplan
```

Services lee `../base/terraform.tfstate` y verifica los digests en ECR al planificar. Se crean API Gateway, grupos de destinos, reglas de red, roles, definiciones y servicios ECS con las imágenes publicadas. También se crea la definición de tarea seed, **pero no se ejecuta automáticamente**. En este primer arranque los health checks de los servicios de datos pueden fallar porque las tablas aún no existen. Ejecutar el siguiente paso antes de esperar que todos los servicios estén estables.

### 7. Crear tablas y cargar los datos sintéticos

Obtener la configuración de la tarea puntual y preparar su red:

```bash
SOLVENTA_SEED=$(terraform -chdir=infra/services output -json seed_task)
SOLVENTA_SEED_DEFINITION=$(jq -er '.task_definition' <<< "$SOLVENTA_SEED")
SOLVENTA_SEED_NETWORK=$(jq -c '{awsvpcConfiguration: {
  subnets: [.subnet], securityGroups: [.security_group], assignPublicIp: "ENABLED"
}}' <<< "$SOLVENTA_SEED")
SOLVENTA_SEED_RESULT=$(aws ecs run-task \
  --cluster "$SOLVENTA_CLUSTER" \
  --launch-type FARGATE \
  --platform-version 1.4.0 \
  --task-definition "$SOLVENTA_SEED_DEFINITION" \
  --network-configuration "$SOLVENTA_SEED_NETWORK" \
  --count 1 --output json)
echo "$SOLVENTA_SEED_RESULT" | jq '{failures, tasks: [.tasks[] | {taskArn, lastStatus}]}'
jq -e '(.failures | length) == 0 and (.tasks | length) == 1' <<< "$SOLVENTA_SEED_RESULT"
SOLVENTA_SEED_TASK=$(jq -er '.tasks[0].taskArn' <<< "$SOLVENTA_SEED_RESULT")
```

Esperar que termine y comprobar el código de salida del contenedor; que una tarea esté detenida no significa que haya terminado correctamente:

```bash
aws ecs wait tasks-stopped --cluster "$SOLVENTA_CLUSTER" --tasks "$SOLVENTA_SEED_TASK"
SOLVENTA_SEED_STATUS=$(aws ecs describe-tasks \
  --cluster "$SOLVENTA_CLUSTER" --tasks "$SOLVENTA_SEED_TASK" --output json)
echo "$SOLVENTA_SEED_STATUS" | jq '.tasks[0] | {stoppedReason, containers}'
jq -e '(.failures | length) == 0 and
  any(.tasks[0].containers[]; .name == "seed" and .exitCode == 0)' <<< "$SOLVENTA_SEED_STATUS"
```

Debe aparecer `exitCode: 0`. La carga crea tablas, catálogo y 1.000 pólizas (`poliza-000001` a `poliza-001000`) en una transacción. Es idempotente y no elimina cotizaciones anteriores. Si el comando de espera vence, consultar la tarea antes de volver a ejecutar seed. [Referencia de ECS RunTask](https://docs.aws.amazon.com/cli/latest/reference/ecs/run-task.html).

### 8. Esperar que el ambiente esté saludable

```bash
aws ecs wait services-stable --cluster "$SOLVENTA_CLUSTER" \
  --services catalogo simulador consulta cotizacion
aws ecs describe-services --cluster "$SOLVENTA_CLUSTER" \
  --services catalogo simulador consulta cotizacion \
  --query 'services[].{service:serviceName,desired:desiredCount,running:runningCount,pending:pendingCount}' \
  --output table
```

En el escenario base deben verse cuatro servicios con `desired=1`, `running=1` y `pending=0`. Si el despliegue inicial quedó marcado como fallido durante la preparación de la base, después de una carga exitosa se puede reiniciar el despliegue en este orden:

```bash
for SOLVENTA_SERVICE in catalogo simulador consulta; do
  aws ecs update-service --cluster "$SOLVENTA_CLUSTER" \
    --service "$SOLVENTA_SERVICE" --force-new-deployment --output json > /dev/null
done
aws ecs wait services-stable --cluster "$SOLVENTA_CLUSTER" --services catalogo simulador consulta
aws ecs update-service --cluster "$SOLVENTA_CLUSTER" \
  --service cotizacion --force-new-deployment --output json > /dev/null
aws ecs wait services-stable --cluster "$SOLVENTA_CLUSTER" --services cotizacion
```

Estos últimos comandos son de recuperación, no hace falta repetirlos si los servicios ya están saludables. Para inspeccionar los destinos de cotización:

```bash
SOLVENTA_TARGET_GROUP=$(terraform -chdir=infra/services output -json experiment_configuration | jq -er '.quotation_target_group')
aws elbv2 describe-target-health --target-group-arn "$SOLVENTA_TARGET_GROUP" \
  --query 'TargetHealthDescriptions[].{ip:Target.Id,state:TargetHealth.State,reason:TargetHealth.Reason}' \
  --output table
```

### 9. Comprobar los recorridos por API Gateway

```bash
SOLVENTA_URL=$(terraform -chdir=infra/services output -raw entry_url)
SOLVENTA_QUOTE=$(curl --fail-with-body --silent --show-error \
  "$SOLVENTA_URL/cotizaciones" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"producto-sintetico"}')
echo "$SOLVENTA_QUOTE" | jq .
SOLVENTA_QUOTE_ID=$(jq -er '.id' <<< "$SOLVENTA_QUOTE")
curl --fail-with-body --silent --show-error "$SOLVENTA_URL/cotizaciones/$SOLVENTA_QUOTE_ID" | jq .
curl --fail-with-body --silent --show-error "$SOLVENTA_URL/consultas/poliza-000001" | jq .
```

Se espera 201 al crear la cotización y 200 en las lecturas. API Gateway agrega `X-Correlation-Id`; puede verse usando `curl -i` y buscarse en los logs. `/health` es una ruta interna de los contenedores, no una ruta publicada por API Gateway. Una respuesta exitosa de estos ejemplos no demuestra todavía los umbrales de rendimiento.

### 10. Logs, parámetros y escenarios

```bash
aws logs tail "/ecs/$SOLVENTA_CLUSTER/cotizacion" --since 10m
aws logs tail "/ecs/$SOLVENTA_CLUSTER/catalogo" --since 10m
aws logs tail "/ecs/$SOLVENTA_CLUSTER/events" --since 10m
aws logs tail "/aws/apigateway/$SOLVENTA_CLUSTER" --since 10m
terraform -chdir=infra/services output dashboard_name
terraform -chdir=infra/services output -json experiment_configuration
```

Los logs de seed se guardan en el grupo de catálogo, en un stream que comienza con `app/seed/`. En CloudWatch → Dashboards, abrir el nombre indicado por Terraform.

Cotización, consulta, catálogo y simulador tienen cada uno una única política de target tracking por CPU (bidireccional: escala hacia afuera y hacia adentro con la misma política). Para cotización: `quotation_replicas` es el mínimo/inicio, `quotation_max_replicas = 3` es el máximo y `quotation_cpu_target = 40` es el objetivo de CPU; `quotation_autoscaling_enabled = true` la activa, con `false` mínimo y máximo quedan en `quotation_replicas` para los escenarios fijos del PDF. `consulta`, `catalogo` y `simulador` usan `backend_autoscaling_enabled`, `backend_max_replicas = 3` y `backend_cpu_target` de la misma forma: sin esto quedan fijos en 1 réplica aunque cotización escale, y `simulador` en particular puede volverse el cuello de botella compartido por todas las réplicas de cotización (ver EXP-ESC-01 auto-002, donde llegó a ~85 % de CPU sin autoescalado propio). Antes se probó combinar la política de CPU con una segunda de `ALBRequestCountPerTarget` (scale-out-only) porque la CPU se quedaba baja mientras el servicio esperaba en el pool de conexiones/latencia externa; con `task_cpu`/`db_pool_size` ya ajustados la CPU sola refleja la carga real, y una sola política evita el conflicto que hacía oscilar a cotización entre 5 y 6 tareas bajo carga sostenida. Revisar el plan y aplicarlo:

```bash
terraform -chdir=infra/services plan -out=scenario.tfplan
terraform -chdir=infra/services apply scenario.tfplan
aws ecs wait services-stable --cluster "$SOLVENTA_CLUSTER" --services cotizacion
```

| Experimento | Réplicas de cotización | Medición posterior |
| --- | --- | --- |
| EXP-ESC-01 | Automático 1–3; fijo 1/2/3 opcional | Rampa de 500 a 50.000 solicitudes/minuto; p95 ≤ 250 ms y errores ≤ 1 %. |
| EXP-DIS-01 | 2 | Detener una tarea bajo carga; éxito ≥ 99 %, p95 ≤ 500 ms, recuperación ≤ 120 s. |
| EXP-LAT-01 | 1 | 500 solicitudes/minuto durante 10 minutos; p95 de cotización ≤ 250 ms y consulta ≤ 150 ms. |

Mantener constantes imágenes/digests, dataset inicial, CPU, memoria y pool; repetir cada escenario tres veces. No reconstruir imágenes entre escenarios. La infraestructura incluye una política para detener tareas de cotización, pero no la asigna a ninguna identidad ni ejecuta fallas. La herramienta de carga se ejecuta localmente y se prepara por separado; estos comandos solo levantan y comprueban el ambiente.

### 11. Problemas frecuentes

| Síntoma | Revisar |
| --- | --- |
| `AccessDenied` | Cuenta/perfil, permisos de creación, publicación ECR y `iam:PassRole` para `run-task`. |
| Credenciales vencidas | Volver a ejecutar `aws sso login --profile solventa` y repetir el comando fallido. |
| `CannotPullContainerError` | Digest publicado, repositorio correcto, arquitectura `linux/amd64`, IP pública y ruta al Internet Gateway. |
| Error al reutilizar un tag | ECR es inmutable; publicar con un tag nuevo y regenerar los digests. |
| `ResourceInitializationError` | Acceso de la tarea a ECR, CloudWatch y Secrets Manager; permisos del rol de ejecución. |
| `relation ... does not exist` o health check 503 | Ejecutar seed y confirmar `exitCode=0`; después esperar o reiniciar el despliegue. |
| `seed_task.task_definition` es `null` | Configurar `seed_command` y aplicar el plan de services. |
| Tiempo agotado de `services-stable` | Eventos ECS, estado del despliegue, logs, cuota de vCPU y salud del ALB. No equivale a un rollback de Terraform. |
| 404 en la entrada | Usar `/cotizaciones` o `/consultas/poliza-000001`; la raíz y `/health` no se publican. |
| 503 en cotización | Catálogo precargado, versión `synthetic-v1`, conectividad Service Connect, demora/timeout del simulador y disponibilidad de PostgreSQL. |
| 429 bajo carga | Throttling de API Gateway o cuotas de la cuenta. |

Para consultar los últimos eventos de un servicio:

```bash
aws ecs describe-services --cluster "$SOLVENTA_CLUSTER" --services cotizacion \
  --query 'services[0].events[0:10]' --output table
```

### 12. Eliminar el ambiente cuando termine el experimento

La eliminación borra los datos sintéticos: RDS está configurado **sin snapshot final**. Guardar antes las evidencias, parámetros y logs que se quieran conservar. Detener únicamente tareas no elimina los costos de ALB y RDS, y ECS volverá a crear tareas si su número deseado sigue siendo mayor que cero.

1. Conservar ambos estados Terraform y sus archivos de variables.
2. Destruir primero las aplicaciones, manteniendo intacto el estado de base:

```bash
terraform -chdir=infra/services plan -destroy -out=destroy.tfplan
terraform -chdir=infra/services apply destroy.tfplan
```

3. Los repositorios ECR usan `force_delete = true`: no hace falta vaciarlos manualmente antes de destruir la base. Si se quiere conservar alguna imagen, copiarla a otro repositorio antes de este paso.
4. Revisar el plan de eliminación de la base y ejecutarlo:

```bash
terraform -chdir=infra/base plan -destroy -out=destroy.tfplan
terraform -chdir=infra/base apply destroy.tfplan
```

Si AWS impide eliminar temporalmente alguna dependencia, leer el error y generar un nuevo plan de destrucción cuando se libere. No borrar el estado para resolverlo. Revisar después que no queden recursos del experimento; backups retenidos o logs creados por servicios fuera de Terraform pueden necesitar limpieza manual.

## Pruebas funcionales antes de la carga

Antes de ejecutar k6, usar la [suite funcional de los cuatro microservicios](tests/smoke/README.md):

```bash
python3 tests/smoke/run.py
```

Verifica ECS/ALB, digests, consulta, creación y lectura de tres cotizaciones, errores esperados y logs correlacionados. Requiere credenciales AWS. Con `--http-only` ejecuta solo los recorridos públicos. Conserva resultados en `tests/smoke/results/`; resolver los fallos antes de iniciar la carga.

## Experimento 1 con k6

El código de EXP-ESC-01 está en [`experiments/exp-esc-01/`](experiments/exp-esc-01/README.md). Incluye rampas de 500 a 50.000 solicitudes/minuto y tres repeticiones explícitas por número de réplicas (`--repetition 1`, `2`, `3`), con preparación de la BD entre ejecuciones, umbrales por nivel, captura de configuración AWS y consolidación de medianas. Seguir su guía después de levantar y verificar este ambiente.

Las guías y runners de los experimentos de esta entrega están en [`experiments/exp-lat-01/`](experiments/exp-lat-01/README.md) y [`experiments/exp-dis-01/`](experiments/exp-dis-01/README.md). EXP-DIS-01 requiere una identidad autorizada para detener una tarea de cotización; los demás accesos de observación pueden ser de solo lectura.

## Validación sin crear recursos

Para revisar exclusivamente el código, sin desplegar ni ejecutar pruebas de carga:

```bash
terraform -chdir=infra/base init -backend=false -input=false
terraform -chdir=infra/base fmt -check
terraform -chdir=infra/base validate
terraform -chdir=infra/services init -backend=false -input=false
terraform -chdir=infra/services fmt -check
terraform -chdir=infra/services validate
docker compose -f src/compose.yaml config --quiet
```

Estas validaciones no garantizan cuotas, permisos, arranque real ni resultados de los experimentos. Para el arranque local con Docker Compose, consultar [`src/README.md`](src/README.md).

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
├── README.md
├── infra/                  # Terraform AWS
├── src/                    # Servicios, Dockerfiles y Compose
├── Dockerfile              # Generador PlantUML
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

La [guía de EXP-ESC-01](experiments/exp-esc-01/README.md#ejecución-recomendada-escalamiento-automático) incluye rampas progresivas, corte por errores, captura del escalamiento y los comandos de reset de la BD entre repeticiones.
