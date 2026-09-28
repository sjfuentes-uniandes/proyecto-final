resource "aws_security_group" "service" {
  for_each    = local.deployed
  name        = "${local.prefix}-${each.key}"
  description = "Tareas de ${each.key}"
  vpc_id      = local.p.vpc_id
}

# Salida: RDS, otros servicios, NAT (aliados y APIs de AWS) y endpoints.
resource "aws_vpc_security_group_egress_rule" "service" {
  for_each          = local.deployed
  security_group_id = aws_security_group.service[each.key].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# El NLB no tiene grupo de seguridad: con destinos IP, el origen es la IP
# privada del NLB dentro de las subredes privadas.
resource "aws_vpc_security_group_ingress_rule" "nlb" {
  for_each = {
    for pair in setproduct([for name, service in local.deployed : name if service.nlb_port != null], range(length(local.p.private_subnet_cidrs))) :
    "${pair[0]}-${pair[1]}" => { service = pair[0], cidr = local.p.private_subnet_cidrs[pair[1]] }
  }
  security_group_id = aws_security_group.service[each.value.service].id
  cidr_ipv4         = each.value.cidr
  ip_protocol       = "tcp"
  from_port         = 8080
  to_port           = 8080
  description       = "NLB privado y health checks"
}

# REST interno por Service Connect: solo los enlaces declarados en el catálogo.
locals {
  service_links = {
    for pair in flatten([
      for caller, service in local.deployed : [
        for callee in service.calls : { from = caller, to = callee } if contains(keys(local.deployed), callee)
      ]
    ]) : "${pair.from}-${pair.to}" => pair
  }
}

resource "aws_vpc_security_group_ingress_rule" "internal" {
  for_each                     = local.service_links
  security_group_id            = aws_security_group.service[each.value.to].id
  referenced_security_group_id = aws_security_group.service[each.value.from].id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
  description                  = "${each.value.from} -> ${each.value.to}"
}

# SQL/TLS: cada servicio con base llega a PostgreSQL; el usuario de la base
# limita el acceso a su propio modelo.
resource "aws_vpc_security_group_ingress_rule" "database" {
  for_each                     = { for name, service in local.deployed : name => service if service.database }
  security_group_id            = local.p.database.security_group_id
  referenced_security_group_id = aws_security_group.service[each.key].id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = each.key
}
