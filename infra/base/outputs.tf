output "ecr_repositories" {
  value = { for name, repo in aws_ecr_repository.service : name => repo.repository_url }
}

output "foundation" {
  description = "Contrato de recursos compartidos consumido por services. No contiene contraseñas."
  value = {
    name              = var.name
    region            = var.aws_region
    account_id        = data.aws_caller_identity.current.account_id
    availability_zone = local.azs[0]
    vpc_id            = aws_vpc.experiment.id
    public_subnet_id  = aws_subnet.public[0].id
    cluster           = { id = aws_ecs_cluster.experiment.id, arn = aws_ecs_cluster.experiment.arn, name = aws_ecs_cluster.experiment.name }
    namespace_arn     = aws_service_discovery_http_namespace.experiment.arn
    ecr               = { for name, repo in aws_ecr_repository.service : name => { arn = repo.arn, url = repo.repository_url, name = repo.name } }
    alb               = { dns_name = aws_lb.entry.dns_name, zone_id = aws_lb.entry.zone_id, arn_suffix = aws_lb.entry.arn_suffix, listener_arn = aws_lb_listener.entry.arn, security_group_id = aws_security_group.alb.id }
    database = {
      host              = aws_db_instance.experiment.address
      port              = aws_db_instance.experiment.port
      name              = aws_db_instance.experiment.db_name
      identifier        = aws_db_instance.experiment.identifier
      secret_arn        = aws_db_instance.experiment.master_user_secret[0].secret_arn
      security_group_id = aws_security_group.database.id
      engine_version    = aws_db_instance.experiment.engine_version_actual
      instance_class    = var.db_instance_class
    }
    events_log_group = aws_cloudwatch_log_group.events.name
  }
}
