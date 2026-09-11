resource "aws_apigatewayv2_api" "experiment" {
  name          = local.base.name
  protocol_type = "HTTP"
}

# Integración pública: sin VPC Link ni contenedor gateway.
resource "aws_apigatewayv2_integration" "alb" {
  api_id                 = aws_apigatewayv2_api.experiment.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = "http://${local.base.alb.dns_name}"
  connection_type        = "INTERNET"
  payload_format_version = "1.0"
  timeout_milliseconds   = 30000
  request_parameters = {
    "overwrite:path"                    = "$request.path"
    "overwrite:header.X-Correlation-Id" = "$context.requestId"
  }
}

resource "aws_apigatewayv2_route" "service" {
  for_each  = toset(flatten([for path in values(local.api_paths) : ["ANY ${path}", "ANY ${path}/{proxy+}"]]))
  api_id    = aws_apigatewayv2_api.experiment.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.alb.id}"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.base.name}"
  retention_in_days = 14
}

resource "aws_apigatewayv2_stage" "experiment" {
  api_id      = aws_apigatewayv2_api.experiment.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    detailed_metrics_enabled = true
    throttling_burst_limit   = 2000
    throttling_rate_limit    = 1000
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId          = "$context.requestId"
      sourceIp           = "$context.identity.sourceIp"
      requestTime        = "$context.requestTime"
      requestTimeEpoch   = "$context.requestTimeEpoch"
      responseLatency    = "$context.responseLatency"
      integrationLatency = "$context.integrationLatency"
      integrationStatus  = "$context.integrationStatus"
      httpMethod         = "$context.httpMethod"
      routeKey           = "$context.routeKey"
      status             = "$context.status"
      responseLength     = "$context.responseLength"
      integrationError   = "$context.integrationErrorMessage"
    })
  }
}
