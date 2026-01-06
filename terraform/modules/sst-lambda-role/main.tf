# ==============================================================================
# SST Lambda Role Module
#
# Creates the IAM role for the Dashborion Lambda function deployed by SST.
# This role is used in semi-managed and managed modes where infrastructure
# is managed by Terraform but deployment is done via SST.
#
# Usage:
#   module "sst_lambda_role" {
#     source = "./modules/sst-lambda-role"
#
#     project_name = "dashborion"
#     environment  = "production"
#
#     cross_account_role_arns = [
#       "arn:aws:iam::111111111111:role/dashborion-read-role",
#       "arn:aws:iam::111111111111:role/dashborion-action-role",
#       "arn:aws:iam::222222222222:role/dashborion-read-role",
#       "arn:aws:iam::222222222222:role/dashborion-action-role",
#     ]
#   }
# ==============================================================================

locals {
  role_name = "${var.project_name}-lambda-role"
}

# -----------------------------------------------------------------------------
# IAM Role for Lambda
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda" {
  name = local.role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = merge(var.tags, {
    Name        = local.role_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

# -----------------------------------------------------------------------------
# Basic Lambda Execution (CloudWatch Logs)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "lambda_basic" {
  name = "${var.project_name}-lambda-basic"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/lambda/${var.project_name}*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Dashboard Read Permissions (same account)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "dashboard_read" {
  name = "${var.project_name}-dashboard-read"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSReadAccess"
        Effect = "Allow"
        Action = [
          "ecs:DescribeClusters",
          "ecs:DescribeServices",
          "ecs:DescribeTasks",
          "ecs:DescribeTaskDefinition",
          "ecs:ListClusters",
          "ecs:ListServices",
          "ecs:ListTasks",
          "ecs:ListTaskDefinitions",
          "ecs:ListTagsForResource"
        ]
        Resource = "*"
      },
      {
        Sid    = "EKSReadAccess"
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters",
          "eks:ListNodegroups",
          "eks:DescribeNodegroup"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchMetricsAccess"
        Effect = "Allow"
        Action = [
          "cloudwatch:GetMetricStatistics",
          "cloudwatch:GetMetricData",
          "cloudwatch:ListMetrics",
          "cloudwatch:DescribeAlarms"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      },
      {
        Sid    = "ELBReadAccess"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:DescribeListeners",
          "elasticloadbalancing:DescribeRules"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudFrontReadAccess"
        Effect = "Allow"
        Action = [
          "cloudfront:ListDistributions",
          "cloudfront:GetDistribution",
          "cloudfront:ListInvalidations",
          "cloudfront:GetInvalidation"
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ReadAccess"
        Effect = "Allow"
        Action = [
          "s3:ListAllMyBuckets",
          "s3:GetBucketLocation",
          "s3:ListBucket",
          "s3:GetObject"
        ]
        Resource = "*"
      },
      {
        Sid    = "RDSReadAccess"
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:DescribeDBClusters",
          "rds:DescribeEvents",
          "rds:ListTagsForResource"
        ]
        Resource = "*"
      },
      {
        Sid    = "ElastiCacheReadAccess"
        Effect = "Allow"
        Action = [
          "elasticache:DescribeCacheClusters",
          "elasticache:DescribeReplicationGroups",
          "elasticache:ListTagsForResource"
        ]
        Resource = "*"
      },
      {
        Sid    = "EC2NetworkReadAccess"
        Effect = "Allow"
        Action = [
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeNatGateways",
          "ec2:DescribeAddresses",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeRouteTables",
          "ec2:DescribeVpcPeeringConnections",
          "ec2:DescribeVpnGateways",
          "ec2:DescribeVpnConnections",
          "ec2:DescribeTransitGatewayVpcAttachments",
          "ec2:DescribeNetworkAcls",
          "ec2:DescribeVpcEndpoints",
          "ec2:DescribeNetworkInterfaces"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudTrailReadAccess"
        Effect = "Allow"
        Action = [
          "cloudtrail:LookupEvents"
        ]
        Resource = "*"
      },
      {
        Sid    = "SecretsManagerReadAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue",
          "secretsmanager:ListSecrets"
        ]
        Resource = "*"
      },
      {
        Sid    = "CodePipelineReadAccess"
        Effect = "Allow"
        Action = [
          "codepipeline:GetPipeline",
          "codepipeline:GetPipelineState",
          "codepipeline:GetPipelineExecution",
          "codepipeline:ListPipelines",
          "codepipeline:ListPipelineExecutions"
        ]
        Resource = "*"
      },
      {
        Sid    = "CodeBuildReadAccess"
        Effect = "Allow"
        Action = [
          "codebuild:BatchGetBuilds",
          "codebuild:BatchGetProjects",
          "codebuild:ListBuildsForProject"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRReadAccess"
        Effect = "Allow"
        Action = [
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
          "ecr:ListImages",
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Dashboard Action Permissions (same account)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "dashboard_actions" {
  name = "${var.project_name}-dashboard-actions"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSDeploymentAccess"
        Effect = "Allow"
        Action = [
          "ecs:UpdateService"
        ]
        Resource = "*"
      },
      {
        Sid    = "RDSStopStartAccess"
        Effect = "Allow"
        Action = [
          "rds:StopDBInstance",
          "rds:StartDBInstance"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudFrontInvalidation"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation"
        ]
        Resource = "*"
      },
      {
        Sid    = "CodePipelineExecution"
        Effect = "Allow"
        Action = [
          "codepipeline:StartPipelineExecution"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Cross-Account Assume Role (if configured)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "cross_account_assume" {
  count = length(var.cross_account_role_arns) > 0 ? 1 : 0

  name = "${var.project_name}-cross-account-assume"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AssumeRoleCrossAccount"
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Resource = var.cross_account_role_arns
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Additional Managed Policies (optional)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "additional" {
  for_each = toset(var.additional_policy_arns)

  role       = aws_iam_role.lambda.name
  policy_arn = each.value
}
