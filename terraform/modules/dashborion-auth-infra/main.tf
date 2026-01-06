# ==============================================================================
# Dashborion Auth Infrastructure Module
#
# Creates DynamoDB tables for permissions and audit logging.
# ==============================================================================

locals {
  permissions_table_name  = coalesce(var.permissions_table_name, "${var.project_name}-permissions")
  audit_table_name        = coalesce(var.audit_table_name, "${var.project_name}-audit")
  device_codes_table_name = coalesce(var.device_codes_table_name, "${var.project_name}-device-codes")
  tokens_table_name       = coalesce(var.tokens_table_name, "${var.project_name}-tokens")

  common_tags = merge(var.tags, {
    Module    = "dashborion-auth-infra"
    ManagedBy = "terraform"
  })
}

# -----------------------------------------------------------------------------
# KMS Key for Encryption (optional)
# -----------------------------------------------------------------------------

resource "aws_kms_key" "dashborion" {
  count = var.enable_encryption && var.kms_key_arn == null ? 1 : 0

  description             = "KMS key for ${var.project_name} auth infrastructure"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow DynamoDB"
        Effect = "Allow"
        Principal = {
          Service = "dynamodb.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_kms_alias" "dashborion" {
  count = var.enable_encryption && var.kms_key_arn == null ? 1 : 0

  name          = "alias/${var.project_name}-auth"
  target_key_id = aws_kms_key.dashborion[0].key_id
}

locals {
  kms_key_arn = var.enable_encryption ? (
    var.kms_key_arn != null ? var.kms_key_arn : aws_kms_key.dashborion[0].arn
  ) : null
}

# -----------------------------------------------------------------------------
# DynamoDB Table: Permissions
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "permissions" {
  name         = local.permissions_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Primary key: USER#{email} / PERM#{project}#{environment}
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI for querying by project/environment
  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "project-env-index"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  # Enable TTL for permission expiration
  ttl {
    attribute_name = "expiresAt"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  dynamic "server_side_encryption" {
    for_each = var.enable_encryption ? [1] : []
    content {
      enabled     = true
      kms_key_arn = local.kms_key_arn
    }
  }

  tags = merge(local.common_tags, {
    Name = local.permissions_table_name
  })
}

# -----------------------------------------------------------------------------
# DynamoDB Table: Audit Log
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "audit" {
  name         = local.audit_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Primary key: USER#{email} / TS#{timestamp}#{action}
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI for querying by project/environment/time
  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "project-time-index"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  # Enable TTL for automatic cleanup
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_point_in_time_recovery
  }

  # Server-side encryption
  dynamic "server_side_encryption" {
    for_each = var.enable_encryption ? [1] : []
    content {
      enabled     = true
      kms_key_arn = local.kms_key_arn
    }
  }

  tags = merge(local.common_tags, {
    Name = local.audit_table_name
  })
}

# -----------------------------------------------------------------------------
# DynamoDB Table: Device Codes (CLI Authentication)
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "device_codes" {
  name         = local.device_codes_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Primary key: DEVICE#{device_code} / USER_CODE#{user_code}
  # Also: USER_CODE#{user_code} / DEVICE#{device_code} for reverse lookup
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # Enable TTL for automatic cleanup (codes expire after 10 minutes)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Server-side encryption
  dynamic "server_side_encryption" {
    for_each = var.enable_encryption ? [1] : []
    content {
      enabled     = true
      kms_key_arn = local.kms_key_arn
    }
  }

  tags = merge(local.common_tags, {
    Name = local.device_codes_table_name
  })
}

# -----------------------------------------------------------------------------
# DynamoDB Table: Tokens (CLI Access Tokens)
# -----------------------------------------------------------------------------

resource "aws_dynamodb_table" "tokens" {
  name         = local.tokens_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  # Primary key: TOKEN#{token_hash} / USER#{email}
  # Also: REFRESH#{refresh_hash} / TOKEN#{token_hash} for refresh lookup
  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # GSI for querying by user email
  attribute {
    name = "email"
    type = "S"
  }

  global_secondary_index {
    name            = "user-tokens-index"
    hash_key        = "email"
    range_key       = "pk"
    projection_type = "ALL"
  }

  # Enable TTL for automatic cleanup
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Server-side encryption
  dynamic "server_side_encryption" {
    for_each = var.enable_encryption ? [1] : []
    content {
      enabled     = true
      kms_key_arn = local.kms_key_arn
    }
  }

  tags = merge(local.common_tags, {
    Name = local.tokens_table_name
  })
}

# -----------------------------------------------------------------------------
# IAM Policy for Lambda Access
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "dynamodb_access" {
  name        = "${var.project_name}-auth-dynamodb-access"
  description = "Policy for accessing Dashborion auth DynamoDB tables"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadPermissions"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:BatchGetItem"
        ]
        Resource = [
          aws_dynamodb_table.permissions.arn,
          "${aws_dynamodb_table.permissions.arn}/index/*"
        ]
      },
      {
        Sid    = "WriteAuditLogs"
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.audit.arn
        ]
      },
      {
        Sid    = "ReadAuditLogs"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.audit.arn,
          "${aws_dynamodb_table.audit.arn}/index/*"
        ]
      },
      {
        Sid    = "DeviceCodesAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.device_codes.arn
        ]
      },
      {
        Sid    = "TokensAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query"
        ]
        Resource = [
          aws_dynamodb_table.tokens.arn,
          "${aws_dynamodb_table.tokens.arn}/index/*"
        ]
      },
      {
        Sid    = "KMSAccess"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.enable_encryption ? [local.kms_key_arn] : []
        Condition = {
          StringEquals = {
            "kms:ViaService" = "dynamodb.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = local.common_tags
}

# Attach policy to Lambda roles
resource "aws_iam_role_policy_attachment" "lambda_dynamodb" {
  for_each = toset(var.lambda_role_arns)

  role       = element(split("/", each.value), length(split("/", each.value)) - 1)
  policy_arn = aws_iam_policy.dynamodb_access.arn
}

# -----------------------------------------------------------------------------
# IAM Policy for Admin Access (permission management)
# -----------------------------------------------------------------------------

resource "aws_iam_policy" "admin_access" {
  name        = "${var.project_name}-auth-admin-access"
  description = "Policy for managing Dashborion auth permissions (admin only)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ManagePermissions"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.permissions.arn,
          "${aws_dynamodb_table.permissions.arn}/index/*"
        ]
      },
      {
        Sid    = "ReadAuditLogs"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.audit.arn,
          "${aws_dynamodb_table.audit.arn}/index/*"
        ]
      }
    ]
  })

  tags = local.common_tags
}

# -----------------------------------------------------------------------------
# Data Sources
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
