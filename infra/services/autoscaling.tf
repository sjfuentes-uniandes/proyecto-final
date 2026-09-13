# Application Auto Scaling controla desiredCount, incluido el modo fijo min=max.
resource "aws_appautoscaling_target" "quotation" {
  min_capacity       = var.quotation_replicas
  max_capacity       = var.quotation_autoscaling_enabled ? var.quotation_max_replicas : var.quotation_replicas
  resource_id        = "service/${local.base.cluster.name}/${aws_ecs_service.quotation["cotizacion"].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Política única y bidireccional (igual patrón que backend_cpu). Antes había
# una segunda política de ALBRequestCountPerTarget porque la CPU se quedaba
# baja mientras el servicio esperaba en el pool de conexiones/latencia externa
# (ver EXP-ESC-01: ScalingActivities vacío con error_rate 42% en hold_3000).
# Con task_cpu y db_pool_size ya corregidos, la CPU sí refleja la carga real y
# alcanza sola para escalar. Combinar dos target tracking policies (una
# scale-out-only) hacía que cotización oscilara entre 5 y 6 tareas bajo carga
# sostenida (17:12-17:31 en auto-002): una sola política elimina ese conflicto.
resource "aws_appautoscaling_policy" "quotation_cpu" {
  count              = var.quotation_autoscaling_enabled ? 1 : 0
  name               = "${local.base.name}-quotation-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.quotation.resource_id
  scalable_dimension = aws_appautoscaling_target.quotation.scalable_dimension
  service_namespace  = aws_appautoscaling_target.quotation.service_namespace
  target_tracking_scaling_policy_configuration {
    target_value       = var.quotation_cpu_target
    scale_out_cooldown = 30
    scale_in_cooldown  = 300
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

locals {
  backend_services = { for name, config in local.deployed_services : name => config if contains(["consulta", "catalogo", "simulador"], name) }
}

# consulta, catálogo y simulador no tenían autoescalado propio: cada réplica de
# cotización llama a la misma instancia fija de simulador/catálogo, así que
# esa dependencia sin escalar limita el throughput total aunque cotización sí
# escale (ver EXP-ESC-01 auto-002: simulador llegó a ~85 % de CPU promedio).
resource "aws_appautoscaling_target" "backend" {
  for_each           = local.backend_services
  min_capacity       = each.value.replicas
  max_capacity       = var.backend_autoscaling_enabled ? var.backend_max_replicas : each.value.replicas
  resource_id        = "service/${local.base.cluster.name}/${aws_ecs_service.backend[each.key].name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  for_each           = var.backend_autoscaling_enabled ? local.backend_services : {}
  name               = "${local.base.name}-${each.key}-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend[each.key].resource_id
  scalable_dimension = aws_appautoscaling_target.backend[each.key].scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend[each.key].service_namespace
  target_tracking_scaling_policy_configuration {
    target_value       = var.backend_cpu_target
    scale_out_cooldown = 30
    scale_in_cooldown  = 300
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}
