resource "aws_lb_target_group" "service" {
  for_each             = toset(["cotizacion", "consulta"])
  name                 = "${local.base.name}-${each.key}"
  port                 = 8080
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = local.base.vpc_id
  deregistration_delay = 5
  health_check {
    path                = "/health"
    matcher             = "200"
    interval            = 5
    timeout             = 2
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

locals {
  api_paths = {
    cotizacion = "/cotizaciones"
    consulta   = "/consultas"
  }
}

resource "aws_lb_listener_rule" "service" {
  for_each     = local.api_paths
  listener_arn = local.base.alb.listener_arn
  priority     = each.key == "cotizacion" ? 10 : 20
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.service[each.key].arn
  }
  condition {
    path_pattern {
      values = [each.value, "${each.value}/*"]
    }
  }
}
