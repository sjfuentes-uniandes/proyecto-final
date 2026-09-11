resource "aws_ecs_cluster" "experiment" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = var.container_insights ? "enabled" : "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "experiment" {
  cluster_name       = aws_ecs_cluster.experiment.name
  capacity_providers = ["FARGATE"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

resource "aws_service_discovery_http_namespace" "experiment" {
  name = var.name
}

