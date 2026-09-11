resource "aws_cloudwatch_log_group" "events" {
  name              = "/ecs/${var.name}/events"
  retention_in_days = 14
}

resource "aws_cloudwatch_event_rule" "ecs" {
  name = "${var.name}-ecs-events"
  event_pattern = jsonencode({
    source        = ["aws.ecs"]
    "detail-type" = ["ECS Task State Change", "ECS Service Action", "ECS Deployment State Change"]
    detail        = { clusterArn = [aws_ecs_cluster.experiment.arn] }
  })
}

resource "aws_cloudwatch_log_resource_policy" "events" {
  policy_name = "${var.name}-ecs-events"
  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = ["events.amazonaws.com", "delivery.logs.amazonaws.com"] }
      Action    = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource  = "${aws_cloudwatch_log_group.events.arn}:*"
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.ecs.arn } }
    }]
  })
}

resource "aws_cloudwatch_event_target" "logs" {
  rule       = aws_cloudwatch_event_rule.ecs.name
  target_id  = "cloudwatch-logs"
  arn        = aws_cloudwatch_log_group.events.arn
  depends_on = [aws_cloudwatch_log_resource_policy.events]
}

