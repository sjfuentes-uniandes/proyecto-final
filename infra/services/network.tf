resource "aws_security_group" "service" {
  for_each = local.services
  name     = "${local.base.name}-${each.key}"
  vpc_id   = local.base.vpc_id
}

resource "aws_vpc_security_group_egress_rule" "service" {
  for_each          = local.services
  security_group_id = aws_security_group.service[each.key].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_egress_rule" "alb" {
  for_each                     = toset(["cotizacion", "consulta"])
  security_group_id            = local.base.alb.security_group_id
  referenced_security_group_id = aws_security_group.service[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}

locals {
  service_links = {
    cotizacion_catalogo  = { from = "cotizacion", to = "catalogo" }
    cotizacion_simulador = { from = "cotizacion", to = "simulador" }
  }
}

resource "aws_vpc_security_group_ingress_rule" "internal" {
  for_each                     = local.service_links
  security_group_id            = aws_security_group.service[each.value.to].id
  referenced_security_group_id = aws_security_group.service[each.value.from].id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}

resource "aws_vpc_security_group_ingress_rule" "database" {
  for_each                     = local.database_services
  security_group_id            = local.base.database.security_group_id
  referenced_security_group_id = aws_security_group.service[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "api_services" {
  for_each                     = toset(["cotizacion", "consulta"])
  security_group_id            = aws_security_group.service[each.key].id
  referenced_security_group_id = local.base.alb.security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}
