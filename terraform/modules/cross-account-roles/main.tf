# ==============================================================================
# Cross-Account Dashboard Roles Module
#
# Creates IAM roles in target accounts that can be assumed by the dashboard
# Lambda function. Two roles are created:
# - Read Role: For read-only operations (ECS, CloudWatch, RDS describe, etc.)
# - Action Role: For write operations (deployments, RDS stop/start, etc.)
#
# Usage:
#   module "cross_account_roles_staging" {
#     source = "./modules/cross-account-roles"
#     providers = { aws = aws.staging }
#
#     project_name       = "dashborion"
#     trusted_account_id = "123456789012"  # Dashboard account
#     target_account_id  = "111111111111"  # Staging account
#     environment        = "staging"
#   }
# ==============================================================================

locals {
  role_name_prefix = var.project_name

  # Default read permissions - comprehensive read access for dashboard monitoring
  default_read_permissions = [
    {
      sid = "ECSReadAccess"
      actions = [
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
      resources = ["*"]
    },
    {
      sid = "CloudWatchMetricsAccess"
      actions = [
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics",
        "cloudwatch:DescribeAlarms"
      ]
      resources = ["*"]
    },
    {
      sid = "CloudWatchLogsAccess"
      actions = [
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ]
      resources = ["*"]
    },
    {
      sid = "ELBReadAccess"
      actions = [
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeRules"
      ]
      resources = ["*"]
    },
    {
      sid = "CloudFrontReadAccess"
      actions = [
        "cloudfront:ListDistributions",
        "cloudfront:GetDistribution",
        "cloudfront:ListInvalidations",
        "cloudfront:GetInvalidation"
      ]
      resources = ["*"]
    },
    {
      sid = "S3ReadAccess"
      actions = [
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "s3:ListBucket"
      ]
      resources = ["*"]
    },
    {
      sid = "RDSReadAccess"
      actions = [
        "rds:DescribeDBInstances",
        "rds:DescribeDBClusters",
        "rds:DescribeEvents",
        "rds:ListTagsForResource"
      ]
      resources = ["*"]
    },
    {
      sid = "ElastiCacheReadAccess"
      actions = [
        "elasticache:DescribeCacheClusters",
        "elasticache:DescribeReplicationGroups",
        "elasticache:ListTagsForResource"
      ]
      resources = ["*"]
    },
    {
      sid = "EC2NetworkReadAccess"
      actions = [
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
      resources = ["*"]
    },
    {
      sid = "CloudTrailReadAccess"
      actions = [
        "cloudtrail:LookupEvents"
      ]
      resources = ["*"]
    },
    {
      sid = "SecretsManagerReadAccess"
      actions = [
        "secretsmanager:DescribeSecret",
        "secretsmanager:ListSecrets"
      ]
      resources = ["*"]
    },
    {
      sid = "CodePipelineReadAccess"
      actions = [
        "codepipeline:GetPipeline",
        "codepipeline:GetPipelineState",
        "codepipeline:GetPipelineExecution",
        "codepipeline:ListPipelines",
        "codepipeline:ListPipelineExecutions"
      ]
      resources = ["*"]
    },
    {
      sid = "CodeBuildReadAccess"
      actions = [
        "codebuild:BatchGetBuilds",
        "codebuild:BatchGetProjects",
        "codebuild:ListBuildsForProject"
      ]
      resources = ["*"]
    },
    {
      sid = "ECRReadAccess"
      actions = [
        "ecr:DescribeRepositories",
        "ecr:DescribeImages",
        "ecr:ListImages",
        "ecr:GetAuthorizationToken"
      ]
      resources = ["*"]
    }
  ]

  # Default action permissions - write access for deployments and management
  default_action_permissions = [
    {
      sid = "ECSDeploymentAccess"
      actions = [
        "ecs:UpdateService",
        "ecs:DescribeServices"
      ]
      resources = ["arn:aws:ecs:*:${var.target_account_id}:service/${var.project_name}-*/*"]
    },
    {
      sid = "ECSClusterAccess"
      actions = [
        "ecs:DescribeClusters"
      ]
      resources = ["arn:aws:ecs:*:${var.target_account_id}:cluster/${var.project_name}-*"]
    },
    {
      sid = "RDSStopStartAccess"
      actions = [
        "rds:StopDBInstance",
        "rds:StartDBInstance",
        "rds:DescribeDBInstances"
      ]
      resources = ["arn:aws:rds:*:${var.target_account_id}:db:${var.project_name}-*"]
    },
    {
      sid = "CloudFrontInvalidation"
      actions = [
        "cloudfront:CreateInvalidation",
        "cloudfront:GetInvalidation",
        "cloudfront:ListDistributions"
      ]
      resources = ["*"]
    },
    {
      sid = "CodePipelineExecution"
      actions = [
        "codepipeline:StartPipelineExecution",
        "codepipeline:GetPipelineState"
      ]
      resources = ["arn:aws:codepipeline:*:${var.target_account_id}:${var.project_name}-*"]
    }
  ]

  # Use custom permissions if provided, otherwise use defaults
  read_permissions   = var.read_permissions != null ? var.read_permissions : local.default_read_permissions
  action_permissions = var.action_permissions != null ? var.action_permissions : local.default_action_permissions
}

# ==============================================================================
# READ ROLE
# ==============================================================================

resource "aws_iam_role" "dashboard_read" {
  name = "${local.role_name_prefix}-read-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = "arn:aws:iam::${var.trusted_account_id}:root"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "sts:ExternalId" = var.project_name
        }
      }
    }]
  })

  tags = merge(var.tags, {
    Name        = "${local.role_name_prefix}-read-role"
    Environment = var.environment
    Purpose     = "Dashboard read access"
  })
}

resource "aws_iam_role_policy" "dashboard_read" {
  name = "${local.role_name_prefix}-read-policy"
  role = aws_iam_role.dashboard_read.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      for perm in local.read_permissions : {
        Sid      = perm.sid
        Effect   = "Allow"
        Action   = perm.actions
        Resource = perm.resources
      }
    ]
  })
}

# ==============================================================================
# ACTION ROLE (optional)
# ==============================================================================

resource "aws_iam_role" "dashboard_action" {
  count = var.enable_action_role ? 1 : 0

  name = "${local.role_name_prefix}-action-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = "arn:aws:iam::${var.trusted_account_id}:root"
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "sts:ExternalId" = var.project_name
        }
      }
    }]
  })

  tags = merge(var.tags, {
    Name        = "${local.role_name_prefix}-action-role"
    Environment = var.environment
    Purpose     = "Dashboard action access (deployments)"
  })
}

resource "aws_iam_role_policy" "dashboard_action" {
  count = var.enable_action_role ? 1 : 0

  name = "${local.role_name_prefix}-action-policy"
  role = aws_iam_role.dashboard_action[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      for perm in local.action_permissions : {
        Sid      = perm.sid
        Effect   = "Allow"
        Action   = perm.actions
        Resource = perm.resources
      }
    ]
  })
}
