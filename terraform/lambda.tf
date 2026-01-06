# ==============================================================================
# Dashboard API Lambda
# ==============================================================================

# Lambda execution role
resource "aws_iam_role" "api_lambda" {
  name = "${local.name_prefix}-api-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = local.stack_tags
}

# Lambda policy
resource "aws_iam_role_policy" "api_lambda" {
  name = "${local.name_prefix}-api-lambda-policy"
  role = aws_iam_role.api_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "sts:AssumeRole"
        ]
        Resource = concat(
          [for role in local.cross_account_roles : role],
          [for role in local.cross_account_action_roles : role],
          [aws_iam_role.dashboard_action.arn]
        )
      },
      {
        Effect = "Allow"
        Action = [
          "codepipeline:GetPipelineState",
          "codepipeline:ListPipelineExecutions",
          "codepipeline:ListPipelines"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:ListBuildsForProject",
          "codebuild:BatchGetBuilds"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/codebuild/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:DescribeImages",
          "ecr:DescribeRepositories"
        ]
        Resource = "*"
      },
      # Action permissions - trigger builds and deployments
      {
        Effect = "Allow"
        Action = [
          "codepipeline:StartPipelineExecution"
        ]
        Resource = "*"
      },
      # Cross-account ECS actions will use assumed role
      {
        Effect = "Allow"
        Action = [
          "ecs:UpdateService",
          "ecs:DescribeServices"
        ]
        Resource = "*"
      },
      # CloudTrail lookup for user attribution on events
      {
        Effect = "Allow"
        Action = [
          "cloudtrail:LookupEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "api_lambda" {
  name              = "/aws/lambda/${local.name_prefix}-api"
  retention_in_days = var.log_retention_days

  tags = local.stack_tags
}

# Lambda package - package entire lambda directory
data "archive_file" "api_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"

  # Exclude unnecessary files from the package
  # Use ** glob pattern for recursive matching of __pycache__ directories
  excludes = concat(
    # Top-level exclusions
    ["_legacy", ".pytest_cache", "tests"],
    # Find all __pycache__ directories dynamically
    [for f in fileset("${path.module}/lambda", "**/__pycache__/**") : f],
    [for f in fileset("${path.module}/lambda", "**/*.pyc") : f]
  )
}

# Lambda function
resource "aws_lambda_function" "api" {
  filename         = data.archive_file.api_lambda.output_path
  function_name    = "${local.name_prefix}-api"
  role             = aws_iam_role.api_lambda.arn
  handler          = "handler.lambda_handler"  # New modular handler
  source_code_hash = data.archive_file.api_lambda.output_base64sha256
  runtime          = "python3.11"
  timeout          = 30
  memory_size      = 512  # Increased for modular code

  environment {
    variables = {
      # Core config
      PROJECT_NAME            = var.project_name
      AWS_REGION_DEFAULT      = var.region
      SHARED_SERVICES_ACCOUNT = data.aws_caller_identity.current.account_id
      SSO_PORTAL_URL          = local.sso_portal_url
      GITHUB_ORG              = var.github_org

      # JSON-encoded configurations
      ENVIRONMENTS            = jsonencode(local.environments)
      CI_PROVIDER             = jsonencode(local.ci_provider)
      ORCHESTRATOR            = jsonencode(local.orchestrator)
      NAMING_PATTERN          = jsonencode(local.naming_pattern)

      # Action role for CloudTrail attribution
      ACTION_ROLE_ARN         = aws_iam_role.dashboard_action.arn
    }
  }

  depends_on = [aws_cloudwatch_log_group.api_lambda]

  tags = local.stack_tags
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.dashboard.execution_arn}/*/*"
}

# ==============================================================================
# Action Role (for CloudTrail attribution with custom RoleSessionName)
# ==============================================================================

# Role that Lambda can assume with a custom session name for user attribution
resource "aws_iam_role" "dashboard_action" {
  name = "${local.name_prefix}-action-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        AWS = aws_iam_role.api_lambda.arn
      }
    }]
  })

  tags = local.stack_tags
}

# Action role policy - permissions for pipeline operations
resource "aws_iam_role_policy" "dashboard_action" {
  name = "${local.name_prefix}-action-policy"
  role = aws_iam_role.dashboard_action.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "codepipeline:StartPipelineExecution",
          "codepipeline:GetPipelineState",
          "codepipeline:ListPipelineExecutions"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:StartBuild",
          "codebuild:BatchGetBuilds"
        ]
        Resource = "*"
      }
    ]
  })
}
