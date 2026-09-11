resource "aws_cloudwatch_metric_alarm" "quotation_latency" {
  alarm_name          = "${local.base.name}-quotation-p95"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  extended_statistic  = "p95"
  period              = 60
  evaluation_periods  = 2
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0.250
  treat_missing_data  = "notBreaching"
  dimensions = {
    LoadBalancer = local.base.alb.arn_suffix
    TargetGroup  = aws_lb_target_group.service["cotizacion"].arn_suffix
  }
  alarm_description = "Latencia del backend, en segundos. El p95 extremo a extremo se mide con la herramienta de carga."
}

resource "aws_cloudwatch_metric_alarm" "quotation_health" {
  alarm_name          = "${local.base.name}-quotation-healthy"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = var.quotation_replicas
  treat_missing_data  = "breaching"
  dimensions = {
    LoadBalancer = local.base.alb.arn_suffix
    TargetGroup  = aws_lb_target_group.service["cotizacion"].arn_suffix
  }
}

resource "aws_cloudwatch_dashboard" "experiment" {
  dashboard_name = local.base.name
  dashboard_body = jsonencode({ widgets = concat([
    for index, metric in ["CPUUtilization", "MemoryUtilization"] : {
      type = "metric", x = index * 12, y = 0, width = 12, height = 6
      properties = {
        title   = "ECS ${metric}", region = local.base.region, period = 60, stat = "Average"
        metrics = [for name in keys(local.services) : ["AWS/ECS", metric, "ClusterName", local.base.cluster.name, "ServiceName", name]]
      }
    }
    ], [
    {
      type = "metric", x = 0, y = 6, width = 12, height = 6
      properties = {
        title   = "ALB entrada: solicitudes y errores", region = local.base.region, period = 60, stat = "Sum"
        metrics = [for metric in ["RequestCount", "HTTPCode_Target_5XX_Count", "HTTPCode_ELB_5XX_Count"] : ["AWS/ApplicationELB", metric, "LoadBalancer", local.base.alb.arn_suffix]]
      }
    },
    {
      type = "metric", x = 12, y = 6, width = 12, height = 6
      properties = {
        title   = "Cotización: percentiles backend (segundos)", region = local.base.region, period = 60
        metrics = [for stat in ["p50", "p90", "p95", "p99"] : ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", local.base.alb.arn_suffix, "TargetGroup", aws_lb_target_group.service["cotizacion"].arn_suffix, { stat = stat }]]
      }
    },
    {
      type = "metric", x = 0, y = 12, width = 12, height = 6
      properties = {
        title   = "Cotización: destinos saludables", region = local.base.region, period = 60, stat = "Minimum"
        metrics = [["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", local.base.alb.arn_suffix, "TargetGroup", aws_lb_target_group.service["cotizacion"].arn_suffix]]
      }
    },
    {
      type = "metric", x = 12, y = 12, width = 12, height = 6
      properties = {
        title   = "RDS: CPU y conexiones", region = local.base.region, period = 60, stat = "Average"
        metrics = [for metric in ["CPUUtilization", "DatabaseConnections"] : ["AWS/RDS", metric, "DBInstanceIdentifier", local.base.database.identifier]]
      }
    },
    {
      type = "log", x = 0, y = 18, width = 24, height = 6
      properties = {
        title = "Reemplazos y eventos ECS", region = local.base.region, view = "table"
        query = "SOURCE '${local.base.events_log_group}' | fields @timestamp, detail.taskArn, detail.lastStatus, detail.stoppedReason | sort @timestamp desc | limit 100"
      }
    }
  ]) })
}

# Se crea sin asignarla: detener tareas requiere una identidad operadora explícita.
resource "aws_iam_policy" "stop_quotation_task" {
  name = "${local.base.name}-stop-quotation-task"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ecs:StopTask"]
      Resource = "arn:${data.aws_partition.current.partition}:ecs:${local.base.region}:${split(":", local.base.cluster.arn)[4]}:task/${local.base.cluster.name}/*"
      Condition = {
        ArnEquals    = { "ecs:cluster" = local.base.cluster.arn }
        StringEquals = { "aws:ResourceTag/ExperimentService" = "cotizacion" }
      }
    }]
  })
}
