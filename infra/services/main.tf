terraform {
  required_version = ">= 1.9.0, < 2.0.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

data "terraform_remote_state" "base" {
  backend = "local"
  config = {
    path = var.base_state_path == null ? "${path.module}/../base/terraform.tfstate" : var.base_state_path
  }
}

locals {
  base = data.terraform_remote_state.base.outputs.foundation
  services = {
    cotizacion = { database = true, replicas = var.quotation_replicas }
    consulta   = { database = true, replicas = 1 }
    catalogo   = { database = true, replicas = 1 }
    simulador  = { database = false, replicas = 1 }
  }
  deployed_services = local.services
  database_services = { for name, config in local.services : name => config if config.database }
}

provider "aws" {
  region              = local.base.region
  allowed_account_ids = [local.base.account_id]
  default_tags {
    tags = { Project = local.base.name, Environment = "architecture-experiment", ManagedBy = "Terraform" }
  }
}

data "aws_partition" "current" {}

# Fallar en plan si un digest no está publicado en el repositorio esperado.
data "aws_ecr_image" "service" {
  for_each        = local.services
  repository_name = local.base.ecr[each.key].name
  image_digest    = var.image_digests[each.key]
}
