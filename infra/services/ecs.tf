resource "aws_cloudwatch_log_group" "service" {
  for_each          = local.services
  name              = "/ecs/${local.base.name}/${each.key}"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "proxy" {
  name              = "/ecs/${local.base.name}/service-connect"
  retention_in_days = 14
}

locals {
  task_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role" "execution" {
  for_each           = local.services
  name               = "${local.base.name}-${each.key}-exec"
  assume_role_policy = local.task_trust
}

resource "aws_iam_role_policy" "execution" {
  for_each = local.services
  role     = aws_iam_role.execution[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
        Resource = local.base.ecr[each.key].arn
      },
      {
        Effect   = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["${aws_cloudwatch_log_group.service[each.key].arn}:*", "${aws_cloudwatch_log_group.proxy.arn}:*"]
      }
      ], each.value.database ? [{
        Effect   = "Allow", Action = ["secretsmanager:GetSecretValue"]
        Resource = local.base.database.secret_arn
    }] : [])
  })
}

resource "aws_iam_role" "task" {
  for_each           = local.services
  name               = "${local.base.name}-${each.key}-task"
  assume_role_policy = local.task_trust
}

locals {
  environment = {
    cotizacion = {
      CATALOG_URL                = "http://catalogo:8080"
      EXTERNAL_SOURCE_URL        = "http://simulador:8080"
      EXTERNAL_SOURCE_TIMEOUT_MS = "150"
      EXTERNAL_SOURCE_RETRIES    = "0"
      RULES_CACHE_ENABLED        = "true"
    }
    consulta  = {}
    catalogo  = { RULES_VERSION = "synthetic-v1" }
    simulador = { RESPONSE_DELAY_MS = "50", FAILURE_RATE = "0" }
  }
  containers = {
    for name, config in local.deployed_services : name => {
      name         = name
      image        = "${local.base.ecr[name].url}@${data.aws_ecr_image.service[name].image_digest}"
      essential    = true
      portMappings = [{ name = "http", containerPort = 8080, protocol = "tcp", appProtocol = "http" }]
      environment = [for key, value in merge(
        { PORT = "8080", SERVICE_NAME = name, LOG_FORMAT = "json", CORRELATION_HEADER = "X-Correlation-Id" },
        local.environment[name],
        config.database ? {
          DB_HOST         = local.base.database.host
          DB_PORT         = tostring(local.base.database.port)
          DB_NAME         = local.base.database.name
          DB_SSLMODE      = "require"
          DB_POOL_SIZE    = tostring(var.db_pool_size)
          DATASET_VERSION = "synthetic-v1"
        } : {}
      ) : { name = key, value = value }]
      secrets = config.database ? [
        { name = "DB_USER", valueFrom = "${local.base.database.secret_arn}:username::" },
        { name = "DB_PASSWORD", valueFrom = "${local.base.database.secret_arn}:password::" }
      ] : []
      healthCheck = {
        command = var.health_check_command, interval = 5, timeout = 2, retries = 2, startPeriod = 30
      }
      stopTimeout = 30
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.service[name].name
          awslogs-region        = local.base.region
          awslogs-stream-prefix = "app"
        }
      }
    }
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each                 = local.deployed_services
  family                   = "${local.base.name}-${each.key}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.task_cpu)
  memory                   = tostring(var.task_memory)
  execution_role_arn       = aws_iam_role.execution[each.key].arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  container_definitions    = jsonencode([local.containers[each.key]])
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  lifecycle {
    precondition {
      condition     = contains(keys(var.image_digests), each.key)
      error_message = "Falta el digest ECR de ${each.key} en image_digests."
    }
  }
}

resource "aws_ecs_service" "backend" {
  for_each                           = { for name, config in local.deployed_services : name => config if contains(["consulta", "catalogo", "simulador"], name) }
  name                               = each.key
  cluster                            = local.base.cluster.id
  task_definition                    = aws_ecs_task_definition.service[each.key].arn
  desired_count                      = each.value.replicas
  propagate_tags                     = "SERVICE"
  tags                               = { ExperimentService = each.key }
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = contains(["consulta", "cotizacion"], each.key) ? 30 : null
  availability_zone_rebalancing      = "DISABLED"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = [local.base.public_subnet_id]
    security_groups  = [aws_security_group.service[each.key].id]
    assign_public_ip = true
  }
  dynamic "load_balancer" {
    for_each = contains(["consulta", "cotizacion"], each.key) ? [each.key] : []
    content {
      target_group_arn = aws_lb_target_group.service[each.key].arn
      container_name   = each.key
      container_port   = 8080
    }
  }
  service_connect_configuration {
    enabled   = true
    namespace = local.base.namespace_arn
    # Cotización y consulta reciben tráfico del ALB.
    dynamic "service" {
      for_each = contains(["catalogo", "simulador"], each.key) ? [each.key] : []
      content {
        port_name      = "http"
        discovery_name = each.key
        client_alias {
          dns_name = each.key
          port     = 8080
        }
      }
    }
    log_configuration {
      log_driver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.proxy.name
        awslogs-region        = local.base.region
        awslogs-stream-prefix = each.key
      }
    }
  }
  depends_on = [
    aws_lb_listener_rule.service,
    aws_iam_role_policy.execution,
  ]
}

resource "aws_ecs_service" "quotation" {
  for_each                           = { for name, config in local.deployed_services : name => config if contains(["cotizacion"], name) }
  name                               = each.key
  cluster                            = local.base.cluster.id
  task_definition                    = aws_ecs_task_definition.service[each.key].arn
  desired_count                      = each.value.replicas
  propagate_tags                     = "SERVICE"
  tags                               = { ExperimentService = each.key }
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  health_check_grace_period_seconds  = contains(["consulta", "cotizacion"], each.key) ? 30 : null
  availability_zone_rebalancing      = "DISABLED"
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  network_configuration {
    subnets          = [local.base.public_subnet_id]
    security_groups  = [aws_security_group.service[each.key].id]
    assign_public_ip = true
  }
  dynamic "load_balancer" {
    for_each = contains(["consulta", "cotizacion"], each.key) ? [each.key] : []
    content {
      target_group_arn = aws_lb_target_group.service[each.key].arn
      container_name   = each.key
      container_port   = 8080
    }
  }
  service_connect_configuration {
    enabled   = true
    namespace = local.base.namespace_arn
    # Cotización y consulta reciben tráfico del ALB.
    dynamic "service" {
      for_each = contains(["catalogo", "simulador"], each.key) ? [each.key] : []
      content {
        port_name      = "http"
        discovery_name = each.key
        client_alias {
          dns_name = each.key
          port     = 8080
        }
      }
    }
    log_configuration {
      log_driver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.proxy.name
        awslogs-region        = local.base.region
        awslogs-stream-prefix = each.key
      }
    }
  }
  depends_on = [
    aws_lb_listener_rule.service,
    aws_iam_role_policy.execution,
    aws_ecs_service.backend
  ]
}

# No ejecuta SQL ni tareas: expone una revisión para una carga posterior explícita.
resource "aws_ecs_task_definition" "seed" {
  count                    = length(var.seed_command) > 0 ? 1 : 0
  family                   = "${local.base.name}-seed"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = tostring(var.task_cpu)
  memory                   = tostring(var.task_memory)
  execution_role_arn       = aws_iam_role.execution["catalogo"].arn
  task_role_arn            = aws_iam_role.task["catalogo"].arn
  container_definitions = jsonencode([merge(
    { for key, value in local.containers["catalogo"] : key => value if !contains(["healthCheck", "portMappings"], key) },
    { name = "seed", command = var.seed_command }
  )])
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
}
