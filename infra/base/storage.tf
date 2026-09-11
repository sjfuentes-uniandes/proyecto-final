resource "aws_ecr_repository" "service" {
  for_each             = local.services
  name                 = "${var.name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_db_subnet_group" "experiment" {
  name       = var.name
  subnet_ids = aws_subnet.database[*].id
}

resource "aws_db_parameter_group" "experiment" {
  name_prefix = "${var.name}-"
  family      = "postgres${split(".", var.postgres_version)[0]}"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "experiment" {
  identifier                      = var.name
  engine                          = "postgres"
  engine_version                  = var.postgres_version
  instance_class                  = var.db_instance_class
  allocated_storage               = 20
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "solventa"
  username                        = "experiment_admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.experiment.name
  parameter_group_name            = aws_db_parameter_group.experiment.name
  vpc_security_group_ids          = [aws_security_group.database.id]
  availability_zone               = local.azs[0]
  multi_az                        = false
  publicly_accessible             = false
  auto_minor_version_upgrade      = false
  backup_retention_period         = 1
  skip_final_snapshot             = true
  deletion_protection             = false
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
}
