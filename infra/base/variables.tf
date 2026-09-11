variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "name" {
  type    = string
  default = "solventa-exp"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,19}$", var.name))
    error_message = "Use de 3 a 20 caracteres: letras minúsculas, números y guiones."
  }
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
  validation {
    condition     = can(cidrsubnet(var.vpc_cidr, 8, 21)) && can(cidrnetmask(var.vpc_cidr))
    error_message = "Indique una red IPv4 que permita crear las subredes del experimento."
  }
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "postgres_version" {
  description = "Versión mayor; registrar la versión exacta resultante antes de medir."
  type        = string
  default     = "16"
}

variable "container_insights" {
  type    = bool
  default = false
}
