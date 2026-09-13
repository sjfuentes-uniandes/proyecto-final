# Terraform: base y servicios independientes

La guía completa de despliegue está en el [README principal](../README.md#levantar-el-ambiente-en-aws). La infraestructura está dividida en dos raíces Terraform; no ejecutar `plan` ni `apply` desde esta carpeta directamente.

| Raíz | Recursos propios | Entradas |
| --- | --- | --- |
| `base/` | VPC, subredes, Internet Gateway, rutas, grupos de seguridad del ALB/RDS, cuatro ECR, RDS y secreto administrado, clúster Fargate vacío, namespace Service Connect, ALB/listener y captura de eventos ECS | Región, nombre, red, tamaño/versión de RDS, Container Insights |
| `services/` | Cuatro servicios y definiciones ECS, tarea seed, roles IAM, logs/proxy, grupos de seguridad y reglas de aplicación, destinos/reglas del ALB, API Gateway, dashboard y alarmas | Estado de base, cuatro digests, CPU/memoria, réplicas, pool y comando seed |

No existe `deploy_services`. La base nunca necesita imágenes, CPU de tareas ni número de réplicas. Los servicios siempre requieren las imágenes correctas. ECR mantiene una lista fija de cuatro repositorios porque deben existir antes de publicar las aplicaciones; crear un repositorio no crea tareas.

## Orden de despliegue

Desde la raíz del repositorio:

```bash
cp infra/base/terraform.tfvars.example infra/base/terraform.tfvars
terraform -chdir=infra/base init
terraform -chdir=infra/base plan -out=base.tfplan
terraform -chdir=infra/base apply base.tfplan
terraform -chdir=infra/base output -json ecr_repositories
```

Copiar el ejemplo solo en la primera configuración. Publicar después las cuatro imágenes en esos repositorios, siguiendo el README principal. Guardar sus digests reales en `infra/services/images.auto.tfvars.json`:

```json
{
  "image_digests": {
    "cotizacion": "sha256:<digest real de 64 caracteres hexadecimales>",
    "consulta": "sha256:<digest real de 64 caracteres hexadecimales>",
    "catalogo": "sha256:<digest real de 64 caracteres hexadecimales>",
    "simulador": "sha256:<digest real de 64 caracteres hexadecimales>"
  }
}
```

Los marcadores anteriores no son digests válidos; el README principal incluye comandos para obtenerlos de ECR automáticamente.

```bash
cp infra/services/terraform.tfvars.example infra/services/terraform.tfvars
terraform -chdir=infra/services init
terraform -chdir=infra/services plan -out=services.tfplan
terraform -chdir=infra/services apply services.tfplan
terraform -chdir=infra/services output -json seed_task
```

El plan comprueba mediante `aws_ecr_image` que cada digest exista en su repositorio; no acepta una configuración parcial. Ejecutar después la tarea seed y esperar los servicios saludables según la guía principal. La tarea seed está definida por defecto y no se ejecuta automáticamente. No medir antes de que la base contenga las tablas y los datos sintéticos.

## Estados y contrato entre despliegues

- `infra/base/terraform.tfstate`: recursos compartidos y outputs `foundation`, `ecr_repositories`.
- `infra/services/terraform.tfstate`: recursos de aplicación y outputs `entry_url`, `experiment_configuration`, `seed_task`, `database`, `dashboard_name`, etc.
- `services` consume el output `foundation` con `terraform_remote_state`, backend local. La ruta predeterminada se resuelve respecto al módulo: `../base/terraform.tfstate`. Se puede indicar otra ruta absoluta mediante `base_state_path`.
- El proveedor de services hereda región y nombre de la base y restringe la cuenta a su `account_id`. No repetir esos valores en otro archivo de variables.
- El contrato exporta IDs, ARNs y metadatos; no exporta la contraseña. Quien lee un estado local puede acceder a su contenido completo: proteger ambos estados.
- Conservar un lockfile por raíz. Los estados, planes, cachés y variables personales están ignorados por Git.

No hay dependencias inversas: base no lee services ni sus imágenes. Un cambio en base requiere aplicar base primero y después revisar el plan de services para consumir los nuevos outputs. Evitar reemplazar VPC/RDS/ALB mientras existan aplicaciones dependientes. Para trabajo en equipo, configurar backends compartidos y adaptar la lectura del estado de base antes de operar concurrentemente.

Referencia: [terraform_remote_state de HashiCorp](https://developer.hashicorp.com/terraform/language/state/remote-state-data).

## Réplicas y experimentos

Cambiar `quotation_replicas` exclusivamente en `infra/services/terraform.tfvars` y aplicar services. `experiments/exp-esc-01/run.py` lee los outputs de esa raíz. La base y las imágenes no cambian al pasar de una a tres réplicas.

Se mantienen tareas públicas con Internet Gateway, RDS privado Single-AZ, HTTP API administrada y un ALB público. No se añade NAT ni EIP. Las rutas son `/cotizaciones` y `/consultas`, con subrutas; las mediciones usan la URL de API Gateway. Los contratos de aplicación y limitaciones se describen en [src/README.md](../src/README.md).

## Eliminar recursos

Destruir **services primero**. Conservar el estado de base durante esa operación. Luego vaciar los cuatro repositorios ECR si las imágenes ya no se necesitan y destruir base. RDS omite snapshot final: conservar evidencias antes de eliminar.

```bash
terraform -chdir=infra/services plan -destroy -out=destroy.tfplan
terraform -chdir=infra/services apply destroy.tfplan
# Después de eliminar explícitamente las imágenes ECR que ya no se necesitan:
terraform -chdir=infra/base plan -destroy -out=destroy.tfplan
terraform -chdir=infra/base apply destroy.tfplan
```

## Validación sin desplegar

```bash
terraform -chdir=infra/base init -backend=false -input=false
terraform -chdir=infra/base fmt -check
terraform -chdir=infra/base validate
terraform -chdir=infra/services init -backend=false -input=false
terraform -chdir=infra/services fmt -check
terraform -chdir=infra/services validate
```

`validate` no requiere imágenes, credenciales ni un estado de base aplicado. En cambio, `plan` de services necesita la base creada y las cuatro imágenes publicadas. No se han ejecutado `plan`, `apply`, migraciones ni cambios en AWS al separar el código.
