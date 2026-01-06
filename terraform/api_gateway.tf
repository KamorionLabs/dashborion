# ==============================================================================
# API Gateway HTTP API
# ==============================================================================

resource "aws_apigatewayv2_api" "dashboard" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization", "X-SSO-User-Email"]
    max_age       = 300
  }

  tags = local.stack_tags
}

# Lambda integration
resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id             = aws_apigatewayv2_api.dashboard.id
  integration_type   = "AWS_PROXY"
  integration_uri    = aws_lambda_function.api.invoke_arn
  integration_method = "POST"
}

# Catch-all GET route for /api/*
resource "aws_apigatewayv2_route" "api" {
  api_id    = aws_apigatewayv2_api.dashboard.id
  route_key = "GET /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# Catch-all POST route for /api/* (actions)
resource "aws_apigatewayv2_route" "api_post" {
  api_id    = aws_apigatewayv2_api.dashboard.id
  route_key = "POST /api/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# Health check route
resource "aws_apigatewayv2_route" "health" {
  api_id    = aws_apigatewayv2_api.dashboard.id
  route_key = "GET /api/health"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# Services list route
resource "aws_apigatewayv2_route" "services" {
  api_id    = aws_apigatewayv2_api.dashboard.id
  route_key = "GET /api/services"
  target    = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
}

# Default stage with auto-deploy
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.dashboard.id
  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }

  tags = local.stack_tags
}

# API Gateway log group
resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = local.stack_tags
}
