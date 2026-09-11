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
  default = 512
  validation {
    condition     = contains([256, 512, 1024, 2048, 4096], var.task_cpu)
    error_message = "CPU permitida: 256, 512, 1024, 2048 o 4096."
  }
}

variable "task_memory" {
  description = "Memoria total de la tarea, incluido el proxy Service Connect."
  type        = number
  default     = 1024
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
  type    = number
  default = 5
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
