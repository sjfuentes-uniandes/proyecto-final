output "entry_url" {
  description = "Endpoint HTTPS administrado de Amazon API Gateway."
  value       = aws_apigatewayv2_api.experiment.api_endpoint
}

output "entry_alb" {
  value = { dns_name = local.base.alb.dns_name, zone_id = local.base.alb.zone_id }
}

output "ecr_repositories" {
  value = { for name, repository in local.base.ecr : name => repository.url }
}

output "experiment_configuration" {
  value = {
    region                 = local.base.region
    availability_zone      = local.base.availability_zone
    cluster                = local.base.cluster.name
    quotation_replicas     = var.quotation_replicas
    task_cpu               = var.task_cpu
    task_memory            = var.task_memory
    image_digests          = var.image_digests
    task_definitions       = { for name, task in aws_ecs_task_definition.service : name => task.arn }
    fargate_platform       = "1.4.0"
    architecture           = "X86_64"
    database_engine        = local.base.database.engine_version
    database_class         = local.base.database.instance_class
    db_pool_size           = var.db_pool_size
    dataset_version        = "synthetic-v1"
    external_delay_ms      = 50
    external_timeout_ms    = 150
    external_retries       = 0
    quotation_target_group = aws_lb_target_group.service["cotizacion"].arn
  }
}

output "database" {
  value = {
    host       = local.base.database.host
    port       = local.base.database.port
    name       = local.base.database.name
    secret_arn = local.base.database.secret_arn
  }
}

output "seed_task" {
  value = {
    task_definition  = try(aws_ecs_task_definition.seed[0].arn, null)
    cluster          = local.base.cluster.arn
    subnet           = local.base.public_subnet_id
    security_group   = aws_security_group.service["catalogo"].id
    assign_public_ip = true
  }
}

output "stop_quotation_policy_arn" {
  value = aws_iam_policy.stop_quotation_task.arn
}

output "dashboard_name" {
  value = aws_cloudwatch_dashboard.experiment.dashboard_name
}
