variable "image_digests" {
  description = "Digests publicados en los repositorios ECR de este módulo, por nombre de servicio."
  type        = map(string)
  validation {
    condition     = toset(keys(var.image_digests)) == toset(["cotizacion", "consulta", "catalogo", "simulador"]) && alltrue([for digest in values(var.image_digests) : can(regex("^sha256:[0-9a-f]{64}$", digest))])
    error_message = "Indique los cuatro servicios. Cada digest debe tener el formato sha256: seguido de 64 caracteres hexadecimales."
  }
}

variable "quotation_replicas" {
  type    = number
  default = 1
  validation {
    condition     = contains([1, 2, 3], var.quotation_replicas)
    error_message = "Los escenarios comparan 1, 2 o 3 tareas de cotización."
  }
}

variable "task_cpu" {
  type    = number
  default = 1024
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.task_cpu)
    error_message = "CPU permitida: 256, 512, 1024, 2048 o 4096."
  }
}

variable "task_memory" {
  description = "Memoria total de la tarea, incluido el proxy Service Connect."
  type        = number
  default     = 2048
  validation {
    condition = contains(lookup({
      "256"  = [512, 1024, 2048]
      "512"  = [1024, 2048, 3072, 4096]
      "1024" = range(2048, 8193, 1024)
      "2048" = range(4096, 16385, 1024)
      "4096" = range(8192, 30721, 1024)
    }, tostring(var.task_cpu), []), var.task_memory)
    error_message = "Seleccione una combinación CPU/memoria válida para Fargate."
  }
}

variable "health_check_command" {
  description = "Contrato de las imágenes: comando ejecutable sin shell que termina en 0 si están saludables."
  type        = list(string)
  default     = ["CMD", "/app/healthcheck"]
}

variable "db_pool_size" {
  # 8 por tarea: con quotation_max_replicas=3 + backend_max_replicas=3 (consulta
  # y catalogo, database=true) el peor caso es 8*(3+3+3)=72 conexiones, bajo el
  # límite de db.t4g.micro (~112 con la fórmula por defecto de RDS Postgres).
  type    = number
  default = 8
  validation {
    condition     = var.db_pool_size >= 1 && floor(var.db_pool_size) == var.db_pool_size
    error_message = "El pool debe ser un entero positivo."
  }
}

variable "seed_command" {
  description = "Comando opcional de migración y carga sintética incluido en la imagen de catálogo; crea una tarea puntual, no la ejecuta."
  type        = list(string)
  default     = ["python", "-m", "app.seed", "--dataset", "synthetic-v1"]
}

variable "base_state_path" {
  description = "Ruta absoluta opcional al estado local de base; por defecto ../base/terraform.tfstate."
  type        = string
  default     = null
}

variable "quotation_autoscaling_enabled" {
  description = "Permite escalar cotización por CPU; false fija min/max en quotation_replicas."
  type        = bool
  default     = true
}
variable "quotation_max_replicas" {
  # El experimento EXP-ESC-01 solo contempla 1 a 3 tareas de cotización.
  type    = number
  default = 3
  validation {
    condition     = var.quotation_max_replicas >= var.quotation_replicas && var.quotation_max_replicas <= 20 && floor(var.quotation_max_replicas) == var.quotation_max_replicas
    error_message = "El máximo debe ser entero, al menos quotation_replicas y no mayor que 20."
  }
}
variable "quotation_cpu_target" {
  # Bajado de 50 a 40: en auto-002 la CPU subió de forma sostenida en los
  # últimos escalones de carga: reaccionar antes evita saturar una tarea
  # mientras se espera a que la política de solicitudes dispare el escalado.
  type    = number
  default = 40
  validation {
    condition     = var.quotation_cpu_target >= 20 && var.quotation_cpu_target <= 80
    error_message = "Usar un objetivo de CPU entre 20 y 80 %."
  }
}
variable "backend_autoscaling_enabled" {
  description = "Habilita autoescalado por CPU para consulta, catálogo y simulador (no solo cotización)."
  type        = bool
  default     = true
}
variable "backend_max_replicas" {
  # simulador (sin autoescalado hasta ahora) llegó a ~85 % de CPU promedio en
  # auto-002 mientras cotización ya escalaba: es una dependencia compartida
  # por todas las réplicas de cotización y puede volverse el cuello de botella.
  type    = number
  default = 3
  validation {
    condition     = var.backend_max_replicas >= 1 && var.backend_max_replicas <= 20 && floor(var.backend_max_replicas) == var.backend_max_replicas
    error_message = "El máximo debe ser entero, al menos 1 y no mayor que 20."
  }
}
variable "backend_cpu_target" {
  type    = number
  default = 50
  validation {
    condition     = var.backend_cpu_target >= 20 && var.backend_cpu_target <= 80
    error_message = "Usar un objetivo de CPU entre 20 y 80 %."
  }
}
