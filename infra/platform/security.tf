# Una clave administrada por el cliente para secretos, RDS, mensajería, logs y
# auditoría. Los roles de tarea reciben kms:Decrypt/GenerateDataKey por IAM; la
# política de clave solo autoriza a los servicios de AWS que cifran en su nombre.
resource "aws_kms_key" "platform" {
  description             = "${local.prefix}: secretos, datos, mensajería y logs"
  enable_key_rotation     = true
  deletion_window_in_days = 7
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountAdministration"
        Effect    = "Allow"
        Principal = { AWS = "arn:${local.partition}:iam::${local.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "CloudWatchLogs"
        Effect    = "Allow"
        Principal = { Service = "logs.${var.aws_region}.amazonaws.com" }
        Action    = ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
        Resource  = "*"
        Condition = {
          ArnLike = { "kms:EncryptionContext:aws:logs:arn" = "arn:${local.partition}:logs:${var.aws_region}:${local.account_id}:log-group:*" }
        }
      },
      {
        # SNS entrega en colas cifradas y CloudWatch publica alarmas en el tópico cifrado.
        Sid       = "MessagingServices"
        Effect    = "Allow"
        Principal = { Service = ["sns.amazonaws.com", "cloudwatch.amazonaws.com", "events.amazonaws.com"] }
        Action    = ["kms:Decrypt", "kms:GenerateDataKey*"]
        Resource  = "*"
        Condition = { StringEquals = { "aws:SourceAccount" = local.account_id } }
      }
    ]
  })
}

resource "aws_kms_alias" "platform" {
  name          = "alias/${local.prefix}"
  target_key_id = aws_kms_key.platform.key_id
}

# Credenciales de aliados. Terraform crea un marcador; el valor real se carga
# fuera de Terraform (consola o CLI) y no queda en el estado.
resource "aws_secretsmanager_secret" "ally" {
  for_each                = local.allies
  name                    = "${local.prefix}/aliados/${each.key}"
  description             = each.value.description
  kms_key_id              = aws_kms_key.platform.arn
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "ally" {
  for_each      = local.allies
  secret_id     = aws_secretsmanager_secret.ally[each.key].id
  secret_string = jsonencode({ client_id = "CAMBIAR", client_secret = "CAMBIAR" })
  lifecycle {
    ignore_changes = [secret_string]
  }
}
