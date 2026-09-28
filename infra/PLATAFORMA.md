# Plataforma Solventa en AWS (historias en Ready)

Infraestructura para ejecutar en AWS las 13 historias de la columna **Ready** del backlog. Se basa en el modelo de despliegue (`docs/diagramas/modelo_despliegue.puml`, `diagrama_despliegue_ecs_fargate.puml`), en la Entrega 8 de arquitectura (componentes, conectores y patrones) y en la organización de la infraestructura del experimento (`infra/base` + `infra/services`), que **no se modifica**.

| Raíz | Qué crea | Depende de |
| --- | --- | --- |
| `infra/platform/` | Red en 2 zonas, NAT, KMS, ECR, RDS PostgreSQL con base y usuario por servicio, clúster ECS y Service Connect, SNS/SQS/DLQ, S3 de auditoría con Object Lock, Cognito, NLB privado + VPC Link + API Gateway REST + WAF, CloudFront para el portal y tópico de alertas | Nada |
| `infra/apps/` | Por cada servicio con imagen publicada: roles IAM, grupos de seguridad, tareas Fargate con colector ADOT, servicios ECS en capas, autoescalado, alarmas y tablero | Estado de `platform` e imágenes en ECR |

El catálogo de servicios vive en un solo lugar: `infra/platform/catalog.tf`. Allí se declaran nivel, puerto del NLB, base de datos, dependencias síncronas, eventos, colas y aliados. `apps` lo recibe por el output `platform`.

## Arquitectura desplegada

```
Portal web ─► CloudFront + S3 (SPA)
Portal web / App móvil ─HTTPS─► WAF ─► API Gateway "canales" ─┐  (JWT Cognito clientes/back-office)
Socio ──HTTPS (+mTLS opc.)──► WAF ─► API Gateway "socios" ────┤  (JWT client_credentials + API key + plan de uso)
                                                              ▼
                                               VPC Link ─► NLB privado (8081/8082/8083)
                                                              ▼
 ┌──────────────────────── ECS Fargate · subredes privadas zonas A y B ────────────────────────┐
 │ bff-web   bff-movil   api-socios          ◄─ capa de acceso                                  │
 │ clientes  catalogo    cotizacion          ◄─ núcleo (REST interno por ECS Service Connect)   │
 │ adaptador-datos  adaptador-identidad      ◄─ adaptadores aislados por aliado (vía NAT)       │
 │ auditoria (worker SQS)   simulador-aliados (WireMock, integración)                           │
 └──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ SQL/TLS                    │ Outbox ─► SNS ─► SQS (+DLQ)        │ HTTPS
        ▼                            ▼                                    ▼
 RDS PostgreSQL (base por servicio)  auditoria / consentimientos-cotizacion  S3 auditoría (Object Lock)
 Secrets Manager + KMS · CloudWatch (logs, EMF, alarmas → SNS alertas) · X-Ray (ADOT)
```

## Trazabilidad historia → infraestructura

| Historia | Recursos |
| --- | --- |
| **HU-W01** Generación de credenciales | Pool Cognito `socios` con servidor de recursos `solventa` y permisos (`partner_scopes`). Un app client `client_credentials` por socio, con secreto generado por Cognito que se muestra una vez. `api-socios` tiene permisos IAM para crear, actualizar o eliminar clientes OAuth y API keys. Respuesta 401 para credenciales inválidas y 403 para permisos no asignados. Pool `backoffice` con grupo `administradores-socios` y MFA obligatorio. |
| **HU-W02** Cuota por cada socio | API REST `socios` con `api_key_required` y planes de uso (`partner_tiers`). El límite y la cuota se aplican **por API key**. 429 con `Retry-After`. Filtro de métricas `Solventa/Socios PartnerThrottled` por `ApiKeyId`. |
| **HU-W10** Datos autorizados | `adaptador-datos` con credenciales en Secrets Manager (`open-finance`, `datos-abiertos`), timeout configurable y salida por NAT. Base `cotizacion` para guardar datos mínimos y su procedencia. |
| **HU-W11** Cálculo perfil de riesgo | Servicios `cotizacion` y `catalogo`, cada uno con su base (versiones de reglas y perfiles). |
| **HU-W12** Consulta fuentes en paralelo | Un adaptador por grupo de aliados (*bulkhead*). `ALLY_*_TIMEOUT_MS` por dependencia. Trazas padre/hijas en X-Ray a través de ADOT. |
| **HU-W27** Correlación de métricas y trazas | API Gateway con X-Ray y logs de acceso JSON (`requestId`, `xrayTraceId`). Encabezado `X-Request-Id` inyectado en cada solicitud. Colector ADOT por tarea (OTLP → X-Ray + EMF). Tablero por ambiente. |
| **HU-W28** Generación de alertas | Tópico SNS `alertas` con correo. Las alarmas envían tanto `ALARM` como `OK`: p95 del perfilamiento > 400 ms, 5XX, p95 del API, destinos saludables, CPU/memoria, atraso de colas, DLQ y RDS. Los umbrales se configuran en variables. |
| **HU-W30** Verificación de identidad | Servicios `clientes` (base propia) y `adaptador-identidad` (secreto `kyc`, timeout propio para distinguir PENDIENTE de RECHAZADO). |
| **HU-W31** Verificación de consentimiento | `clientes` guarda los consentimientos y `cotizacion` los consulta antes de llamar al adaptador. La cola `consentimientos-cotizacion` invalida cachés cuando se revoca un consentimiento. Las decisiones quedan en la auditoría inmutable. |
| **HU-M06** Validación de cliente | Ruta `/movil/*` → `bff-movil` → `clientes` → `adaptador-identidad`. La regla WAF de tamaño de cuerpo queda en modo conteo para permitir la selfie. No se guarda biometría en AWS. |
| **HU-M07** Ingreso biométrico | Cliente Cognito `app-movil` (PKCE, `enable_token_revocation`). La biometría del sistema operativo desbloquea el refresh token; revocarlo obliga a una autenticación completa. |
| **HU-M08** Registro de autorización | `clientes` + Outbox → SNS → SQS `auditoria` → worker `auditoria` → S3 con Object Lock (versionado, KMS, solo TLS). |
| **HU-M09** Revocación de consentimiento | Igual que HU-M08, más la cola `consentimientos-cotizacion`. |

Transversal (ARQ-001/002/003): tareas repartidas en dos zonas con rebalanceo, circuito de despliegue con rollback, Service Connect, autoescalado (APIs por CPU y workers por profundidad de cola), RDS Multi-AZ con `high_availability = true`, cifrado con KMS y secretos fuera de las imágenes.

## Decisiones y costos (perfil por defecto: mínimo costo)

- **Un solo NAT Gateway** (unos 33 USD/mes más el tráfico). Es más barato que los endpoints de interfaz (unos 7 USD/mes por servicio y zona). Además, los adaptadores (aliados reales) y `api-socios` (plano de control de Cognito y API Gateway) necesitan salida a Internet. El endpoint *gateway* de S3 es gratuito y siempre se crea. `interface_endpoints` permite agregar endpoints si se requiere tráfico privado.
- **RDS `db.t4g.micro` Single-AZ** con una base y un usuario por servicio en la misma instancia. `high_availability = true` activa Multi-AZ (standby síncrono) y un NAT por zona.
- **1 réplica por servicio**, con base en FARGATE y excedente en FARGATE_SPOT. `min_replicas = 2` deja una réplica activa en cada zona (redundancia activa, HU-W29).
- **API Gateway REST en lugar de HTTP API**: los planes de uso, las API keys y WAF solo existen en REST. REST exige **NLB** para el VPC Link, como indica la tabla de nodos de la Entrega 8.
- **Dos APIs** (`canales` y `socios`): el mTLS aplica a todo un dominio. Separarlos permite exigir certificado solo a los socios y desactivar el endpoint `execute-api` del API de socios cuando existe dominio propio.
- **WAF** activo por defecto (unos 5 USD/mes + 1 USD por regla). **Container Insights** desactivado (`container_insights`).
- **Caché de catálogo (ElastiCache)**, **proyección CQRS**, **Saga** y **evidencias de siniestros** no se crean porque ninguna historia en Ready los usa. El catálogo permite agregarlos después.

Costo orientativo del ambiente vacío (us-east-1): NAT ~33, WAF ~9, RDS micro ~13, NLB ~17, KMS ~1 y CloudFront/Cognito/SNS/SQS casi 0 en volumen de pruebas, **≈ 75 USD/mes** antes de las tareas. Cada tarea de 0,25 vCPU / 1 GB cuesta ≈ 9 USD/mes en FARGATE (menos en SPOT). Para ahorrar, **destruir el ambiente cuando no se use**.

## Despliegue

Requisitos: Terraform ≥ 1.9, AWS CLI v2, Docker y credenciales con permisos de administración en la cuenta.

```bash
# 1. Plataforma
cp infra/platform/terraform.tfvars.example infra/platform/terraform.tfvars
terraform -chdir=infra/platform init
terraform -chdir=infra/platform plan -out=platform.tfplan
terraform -chdir=infra/platform apply platform.tfplan
```

`aws_api_gateway_account` fija el rol de logs de API Gateway **para toda la región de la cuenta**. Si otra pila ya lo administra, eliminar ese recurso de una de las dos.

```bash
# 2. Crear bases y usuarios por servicio (idempotente; repetir al agregar un servicio con base)
eval "$(terraform -chdir=infra/platform output -json db_bootstrap_task | jq -r '"CLUSTER=\(.cluster) TASK=\(.task_definition) SUBNETS=\(.subnets|join(",")) SG=\(.security_group)"')"
aws ecs run-task --cluster "$CLUSTER" --task-definition "$TASK" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}"
# Revisar el resultado en el log group /ecs/<prefijo>/db-bootstrap

# 3. Cargar las credenciales reales de los aliados (opcional; sin ellas se usa el simulador)
aws secretsmanager put-secret-value --secret-id solventa-int/aliados/kyc \
  --secret-string '{"client_id":"...","client_secret":"..."}'
```

```bash
# 4. Publicar imágenes (solo las de los servicios listos) y registrar sus digests
REGION=us-east-1
REPOS=$(terraform -chdir=infra/platform output -json ecr_repositories)
REGISTRY=$(echo "$REPOS" | jq -r 'first(.[]) | split("/")[0]')
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"

# Por cada servicio listo (etiquetas inmutables):
#   docker build --platform linux/amd64 -t "$(echo "$REPOS" | jq -r '.clientes'):v1" <ruta-del-servicio>
#   docker push "$(echo "$REPOS" | jq -r '.clientes'):v1"

# Registrar el último digest de cada repositorio que ya tiene imagen:
echo "$REPOS" | jq -r 'to_entries[] | "\(.key) \(.value | split("/")[1:] | join("/"))"' |
while read -r svc repo; do
  digest=$(aws ecr describe-images --repository-name "$repo" \
    --query 'sort_by(imageDetails,&imagePushedAt)[-1].imageDigest' --output text 2>/dev/null)
  [ -n "$digest" ] && [ "$digest" != "None" ] && jq -n --arg k "$svc" --arg v "$digest" '{($k): $v}'
done | jq -s '{image_digests: (add // {})}' > infra/apps/images.auto.tfvars.json

# 5. Aplicaciones
cp infra/apps/terraform.tfvars.example infra/apps/terraform.tfvars
terraform -chdir=infra/apps init
terraform -chdir=infra/apps plan -out=apps.tfplan
terraform -chdir=infra/apps apply apps.tfplan
terraform -chdir=infra/apps output pending_services   # servicios sin imagen todavía
```

**Despliegue parcial:** `apps` solo crea los servicios presentes en `image_digests`, así que cada historia puede habilitar su servicio cuando tenga imagen. Service Connect solo entrega a una tarea los endpoints que existían cuando arrancó. Por eso `apps` calcula capas de dependencia y crea primero a los servicios invocados. Si un servicio nuevo cambia de capa, Terraform lo recrea. Cuando se agrega un servicio invocado por otros que ya estaban corriendo, forzar un nuevo despliegue de quienes lo llaman (`aws ecs update-service --force-new-deployment`).

**Portal web:** `aws s3 sync dist/ s3://$(terraform -chdir=infra/platform output -json web | jq -r .bucket)` y después invalidar CloudFront. La configuración OAuth pública está en `terraform -chdir=infra/platform output cognito`.

**Socios de prueba (HU-W01/W02 N2/N3):** declarar `partners` en `terraform.tfvars` y leer las credenciales con `terraform -chdir=infra/platform output -json partners`. Obtener el token con `client_credentials` en `cognito.partners.token_url` y llamar al API de socios con `Authorization: Bearer <token>` y `x-api-key: <api_key>`.

## Contratos para los servicios

**Imágenes:** escuchan en el puerto `8080`, exponen `GET /health` e incluyen `/app/healthcheck`, igual que en el experimento.

**Variables de entorno** (definidas en `infra/apps/ecs.tf`):

| Variable | Servicios | Contenido |
| --- | --- | --- |
| `SERVICE_NAME`, `ENVIRONMENT`, `CORRELATION_HEADER`, `REQUEST_ID_HEADER` | Todos | Identidad del servicio y encabezados de correlación (`X-Correlation-Id`; si no llega, usar `X-Request-Id` de API Gateway) |
| `<DEPENDENCIA>_URL` | Según `calls` | `http://<servicio>:8080` por Service Connect, por ejemplo `CLIENTES_URL` |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | Con base | Base y usuario propios (secretos inyectados por ECS) |
| `EVENTS_TOPIC_ARN`, `OUTBOX_ENABLED` | Publicadores | Tópico de eventos de negocio |
| `SQS_<COLA>_URL` | Consumidores | Por ejemplo `SQS_AUDITORIA_URL` |
| `ALLY_<ALIADO>_URL`, `ALLY_<ALIADO>_TIMEOUT_MS`, `ALLY_<ALIADO>_CREDENTIALS` | Adaptadores | Endpoint, timeout y JSON de credenciales |
| `AUDIT_BUCKET` | auditoria | Bucket con Object Lock |
| `PARTNERS_USER_POOL_ID`, `PARTNERS_API_ID`, `PARTNERS_USAGE_PLANS`, `PARTNERS_TOKEN_URL` | api-socios | Alta de socios y asignación de plan |
| `JWT_ISSUERS` | Acceso | Emisores válidos para revalidar el token (defensa en profundidad) |
| `OTEL_*` | Todos | Exportación OTLP a `localhost:4317` (colector ADOT) |

**Encabezados que agrega API Gateway** a partir del token validado (sobrescriben lo que envíe el cliente): `X-Authenticated-Sub` (canales), `X-Partner-Client-Id`, `X-Partner-Scopes` y `X-Partner-Key-Id` (socios). `api-socios` responde 403 cuando el permiso requerido no está en `X-Partner-Scopes` (HU-W01 AC4).

**Eventos:** el relay del Outbox publica en SNS con el atributo de mensaje `eventType` (`String`), por ejemplo `ConsentimientoOtorgado`, `ConsentimientoRevocado` o `IdentidadVerificada`. El cuerpo es el sobre del evento con `eventId`, que los consumidores usan para la idempotencia. La cola `auditoria` recibe todos los eventos; `consentimientos-cotizacion` recibe solo los `Consentimiento*`.

**Métricas** (usadas por alarmas y tablero): espacio de nombres `Solventa`, dimensiones `Environment`, `Service` y `Operation`. Los servicios publican con OpenTelemetry:
- `OperationDuration`: histograma en ms. `OTEL_EXPORTER_OTLP_METRICS_DEFAULT_HISTOGRAM_AGGREGATION` ya lo configura como exponencial, lo que permite calcular p95.
- `OperationErrors`: contador.

El perfilamiento debe usar `Service=cotizacion` y `Operation=perfilamiento`.

**Logs:** JSON por línea con `service`, `operation`, `result`, `duration_ms` y `correlation_id`. Nunca incluir secretos, tokens, biometría ni payloads financieros completos (HU-W27 AC4).

## Probar la alerta sin carga (HU-W28 AC4)

```bash
aws cloudwatch put-metric-data --namespace Solventa --metric-name OperationDuration --unit Milliseconds \
  --dimensions Environment=int,Service=cotizacion,Operation=perfilamiento \
  --values 900 950 1000 --counts 20 20 20
# Repetir cada minuto durante 3-5 minutos: la alarma pasa a ALARM y notifica.
# Al dejar de publicar (treat_missing_data = notBreaching) vuelve a OK y notifica la recuperación.
```

## Validación sin desplegar

```bash
for root in platform apps; do
  terraform -chdir=infra/$root init -backend=false -input=false
  terraform -chdir=infra/$root fmt -check -recursive
  terraform -chdir=infra/$root validate
  terraform -chdir=infra/$root test   # plan completo con proveedores simulados, sin credenciales
done
```

## Eliminar el ambiente

Destruir primero **apps** y después **platform**. Con `audit_lock_mode = "GOVERNANCE"`, Terraform puede vaciar el bucket de auditoría. Con `COMPLIANCE`, los objetos no se pueden borrar antes de que venza su retención.

```bash
terraform -chdir=infra/apps destroy
terraform -chdir=infra/platform destroy
```
