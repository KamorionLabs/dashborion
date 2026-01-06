# ==============================================================================
# SST Deployment Role Module
#
# Creates an IAM role that SST/Pulumi can assume to deploy Dashborion.
# Permissions vary based on the deployment mode:
#
# - standalone: Full permissions to create all resources (S3, CloudFront, Lambda, IAM, API Gateway)
# - semi-managed: Create S3/CloudFront/Lambda/API Gateway, PassRole to external Lambda role
# - managed: Sync S3, invalidate CloudFront, update Lambda code
#
# Usage:
#   module "sst_deploy_role" {
#     source = "./modules/sst-deploy-role"
#
#     project_name = "dashborion"
#     mode         = "semi-managed"
#
#     trusted_principals = [
#       "arn:aws:iam::123456789012:user/deployer",
#       "arn:aws:iam::123456789012:role/github-actions"
#     ]
#
#     lambda_role_arn = "arn:aws:iam::123456789012:role/dashborion-lambda-role"
#   }
# ==============================================================================

locals {
  role_name = "${var.project_name}-sst-deploy-role"

  # Build trust policy based on principals and services
  trust_statements = concat(
    length(var.trusted_principals) > 0 ? [{
      Effect = "Allow"
      Principal = {
        AWS = var.trusted_principals
      }
      Action = "sts:AssumeRole"
    }] : [],
    length(var.trusted_services) > 0 ? [{
      Effect = "Allow"
      Principal = {
        Service = var.trusted_services
      }
      Action = "sts:AssumeRole"
    }] : []
  )
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "sst_deploy" {
  name = local.role_name

  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.trust_statements
  })

  tags = merge(var.tags, {
    Name        = local.role_name
    Purpose     = "SST deployment role"
    Mode        = var.mode
    ManagedBy   = "terraform"
  })
}

# -----------------------------------------------------------------------------
# SST/Pulumi State Management (all modes)
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "sst_state" {
  name = "${var.project_name}-sst-state"
  role = aws_iam_role.sst_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SSTStateS3"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = var.state_bucket_name != null ? [
          "arn:aws:s3:::${var.state_bucket_name}",
          "arn:aws:s3:::${var.state_bucket_name}/*"
        ] : [
          "arn:aws:s3:::sst-state-*",
          "arn:aws:s3:::sst-state-*/*"
        ]
      },
      {
        Sid    = "SSTStateDynamoDB"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = "arn:aws:dynamodb:*:*:table/sst-*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# STANDALONE MODE - Full permissions to create everything
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "standalone_permissions" {
  count = var.mode == "standalone" ? 1 : 0

  name = "${var.project_name}-standalone-deploy"
  role = aws_iam_role.sst_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 - Create and manage buckets
      {
        Sid    = "S3FullAccess"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:DeleteBucket",
          "s3:PutBucketPolicy",
          "s3:GetBucketPolicy",
          "s3:DeleteBucketPolicy",
          "s3:PutBucketAcl",
          "s3:GetBucketAcl",
          "s3:PutBucketCORS",
          "s3:GetBucketCORS",
          "s3:PutBucketWebsite",
          "s3:GetBucketWebsite",
          "s3:DeleteBucketWebsite",
          "s3:PutBucketVersioning",
          "s3:GetBucketVersioning",
          "s3:PutBucketPublicAccessBlock",
          "s3:GetBucketPublicAccessBlock",
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:PutBucketTagging",
          "s3:GetBucketTagging"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-*",
          "arn:aws:s3:::${var.project_name}-*/*"
        ]
      },
      # CloudFront - Create and manage distributions
      {
        Sid    = "CloudFrontFullAccess"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateDistribution",
          "cloudfront:UpdateDistribution",
          "cloudfront:DeleteDistribution",
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:ListDistributions",
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
          "cloudfront:ListInvalidations",
          "cloudfront:TagResource",
          "cloudfront:UntagResource",
          "cloudfront:ListTagsForResource",
          "cloudfront:CreateOriginAccessControl",
          "cloudfront:UpdateOriginAccessControl",
          "cloudfront:DeleteOriginAccessControl",
          "cloudfront:GetOriginAccessControl",
          "cloudfront:ListOriginAccessControls"
        ]
        Resource = "*"
      },
      # Lambda - Create and manage functions
      {
        Sid    = "LambdaFullAccess"
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:DeleteFunction",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:ListFunctions",
          "lambda:InvokeFunction",
          "lambda:AddPermission",
          "lambda:RemovePermission",
          "lambda:GetPolicy",
          "lambda:TagResource",
          "lambda:UntagResource",
          "lambda:ListTags",
          "lambda:PublishVersion",
          "lambda:CreateAlias",
          "lambda:UpdateAlias",
          "lambda:DeleteAlias",
          "lambda:GetAlias"
        ]
        Resource = "arn:aws:lambda:*:*:function:${var.project_name}-*"
      },
      # IAM - Create Lambda execution roles
      {
        Sid    = "IAMRoleManagement"
        Effect = "Allow"
        Action = [
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:UpdateRole",
          "iam:PassRole",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:TagRole",
          "iam:UntagRole"
        ]
        Resource = "arn:aws:iam::*:role/${var.project_name}-*"
      },
      # API Gateway - Create and manage APIs
      {
        Sid    = "APIGatewayFullAccess"
        Effect = "Allow"
        Action = [
          "apigateway:POST",
          "apigateway:GET",
          "apigateway:PUT",
          "apigateway:DELETE",
          "apigateway:PATCH",
          "apigateway:TagResource",
          "apigateway:UntagResource"
        ]
        Resource = [
          "arn:aws:apigateway:*::/apis",
          "arn:aws:apigateway:*::/apis/*",
          "arn:aws:apigateway:*::/tags/*"
        ]
      },
      # CloudWatch Logs - Create log groups for Lambda
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy",
          "logs:TagLogGroup",
          "logs:UntagLogGroup",
          "logs:DescribeLogGroups"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/lambda/${var.project_name}-*"
      },
      # ACM - For custom domains
      {
        Sid    = "ACMReadAccess"
        Effect = "Allow"
        Action = [
          "acm:ListCertificates",
          "acm:DescribeCertificate",
          "acm:GetCertificate"
        ]
        Resource = "*"
      },
      # Route53 - For custom domains
      {
        Sid    = "Route53Access"
        Effect = "Allow"
        Action = [
          "route53:ListHostedZones",
          "route53:GetHostedZone",
          "route53:ChangeResourceRecordSets",
          "route53:ListResourceRecordSets"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# SEMI-MANAGED MODE - Create S3/CloudFront/Lambda, but PassRole to external role
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "semi_managed_permissions" {
  count = var.mode == "semi-managed" ? 1 : 0

  name = "${var.project_name}-semi-managed-deploy"
  role = aws_iam_role.sst_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 - Create and manage buckets
      {
        Sid    = "S3FullAccess"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:DeleteBucket",
          "s3:PutBucketPolicy",
          "s3:GetBucketPolicy",
          "s3:DeleteBucketPolicy",
          "s3:PutBucketAcl",
          "s3:GetBucketAcl",
          "s3:PutBucketCORS",
          "s3:GetBucketCORS",
          "s3:PutBucketWebsite",
          "s3:GetBucketWebsite",
          "s3:DeleteBucketWebsite",
          "s3:PutBucketVersioning",
          "s3:GetBucketVersioning",
          "s3:PutBucketPublicAccessBlock",
          "s3:GetBucketPublicAccessBlock",
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:PutBucketTagging",
          "s3:GetBucketTagging"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-*",
          "arn:aws:s3:::${var.project_name}-*/*"
        ]
      },
      # CloudFront - Create and manage distributions
      {
        Sid    = "CloudFrontFullAccess"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateDistribution",
          "cloudfront:UpdateDistribution",
          "cloudfront:DeleteDistribution",
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig",
          "cloudfront:ListDistributions",
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
          "cloudfront:ListInvalidations",
          "cloudfront:TagResource",
          "cloudfront:UntagResource",
          "cloudfront:ListTagsForResource",
          "cloudfront:CreateOriginAccessControl",
          "cloudfront:UpdateOriginAccessControl",
          "cloudfront:DeleteOriginAccessControl",
          "cloudfront:GetOriginAccessControl",
          "cloudfront:ListOriginAccessControls"
        ]
        Resource = "*"
      },
      # Lambda - Create functions but use external role
      {
        Sid    = "LambdaFunctionAccess"
        Effect = "Allow"
        Action = [
          "lambda:CreateFunction",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:DeleteFunction",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:ListFunctions",
          "lambda:InvokeFunction",
          "lambda:AddPermission",
          "lambda:RemovePermission",
          "lambda:GetPolicy",
          "lambda:TagResource",
          "lambda:UntagResource",
          "lambda:ListTags",
          "lambda:PublishVersion",
          "lambda:CreateAlias",
          "lambda:UpdateAlias",
          "lambda:DeleteAlias",
          "lambda:GetAlias"
        ]
        Resource = "arn:aws:lambda:*:*:function:${var.project_name}-*"
      },
      # IAM - Only PassRole to external Lambda role (no CreateRole)
      {
        Sid    = "IAMPassRole"
        Effect = "Allow"
        Action = [
          "iam:PassRole",
          "iam:GetRole"
        ]
        Resource = var.lambda_role_arn != null ? var.lambda_role_arn : "arn:aws:iam::*:role/${var.project_name}-lambda-role"
      },
      # API Gateway - Create and manage APIs
      {
        Sid    = "APIGatewayFullAccess"
        Effect = "Allow"
        Action = [
          "apigateway:POST",
          "apigateway:GET",
          "apigateway:PUT",
          "apigateway:DELETE",
          "apigateway:PATCH",
          "apigateway:TagResource",
          "apigateway:UntagResource"
        ]
        Resource = [
          "arn:aws:apigateway:*::/apis",
          "arn:aws:apigateway:*::/apis/*",
          "arn:aws:apigateway:*::/tags/*"
        ]
      },
      # CloudWatch Logs - Create log groups for Lambda
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:DeleteLogGroup",
          "logs:PutRetentionPolicy",
          "logs:DeleteRetentionPolicy",
          "logs:TagLogGroup",
          "logs:UntagLogGroup",
          "logs:DescribeLogGroups"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/lambda/${var.project_name}-*"
      },
      # ACM - For custom domains
      {
        Sid    = "ACMReadAccess"
        Effect = "Allow"
        Action = [
          "acm:ListCertificates",
          "acm:DescribeCertificate",
          "acm:GetCertificate"
        ]
        Resource = "*"
      },
      # Route53 - For custom domains
      {
        Sid    = "Route53Access"
        Effect = "Allow"
        Action = [
          "route53:ListHostedZones",
          "route53:GetHostedZone",
          "route53:ChangeResourceRecordSets",
          "route53:ListResourceRecordSets"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# MANAGED MODE - Minimal permissions: sync S3, invalidate CloudFront, update Lambda
# -----------------------------------------------------------------------------

resource "aws_iam_role_policy" "managed_permissions" {
  count = var.mode == "managed" ? 1 : 0

  name = "${var.project_name}-managed-deploy"
  role = aws_iam_role.sst_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 - Sync objects to existing bucket only
      {
        Sid    = "S3SyncAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = var.s3_bucket_arn != null ? [
          var.s3_bucket_arn,
          "${var.s3_bucket_arn}/*"
        ] : [
          "arn:aws:s3:::${var.project_name}-*",
          "arn:aws:s3:::${var.project_name}-*/*"
        ]
      },
      # CloudFront - Invalidation only
      {
        Sid    = "CloudFrontInvalidation"
        Effect = "Allow"
        Action = [
          "cloudfront:CreateInvalidation",
          "cloudfront:GetInvalidation",
          "cloudfront:ListInvalidations",
          "cloudfront:GetDistribution",
          "cloudfront:GetDistributionConfig"
        ]
        Resource = var.cloudfront_distribution_arn != null ? var.cloudfront_distribution_arn : "*"
      },
      # Lambda - Update code and config only
      {
        Sid    = "LambdaUpdateAccess"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:PublishVersion",
          "lambda:UpdateAlias"
        ]
        Resource = "arn:aws:lambda:*:*:function:${var.project_name}-*"
      },
      # IAM - PassRole to external Lambda role
      {
        Sid    = "IAMPassRole"
        Effect = "Allow"
        Action = [
          "iam:PassRole",
          "iam:GetRole"
        ]
        Resource = var.lambda_role_arn != null ? var.lambda_role_arn : "arn:aws:iam::*:role/${var.project_name}-lambda-role"
      },
      # API Gateway - Update only (no create/delete)
      {
        Sid    = "APIGatewayUpdateAccess"
        Effect = "Allow"
        Action = [
          "apigateway:GET",
          "apigateway:PUT",
          "apigateway:PATCH"
        ]
        Resource = [
          "arn:aws:apigateway:*::/apis",
          "arn:aws:apigateway:*::/apis/*"
        ]
      }
    ]
  })
}
