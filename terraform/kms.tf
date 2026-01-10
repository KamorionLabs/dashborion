# ==============================================================================
# KMS Key for Authentication Encryption
# ==============================================================================
#
# Used to encrypt:
# - Session data in DynamoDB
# - Token metadata (email, permissions)
# - Refresh tokens
#

resource "aws_kms_key" "auth" {
  description             = "${local.name_prefix} authentication encryption key"
  enable_key_rotation     = true
  deletion_window_in_days = 7

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRootAccountFullAccess"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowLambdaEncryptDecrypt"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.lambda.arn
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = merge(local.common_tags, {
    Name    = "${local.name_prefix}-auth-key"
    Purpose = "auth-encryption"
  })
}

resource "aws_kms_alias" "auth" {
  name          = "alias/${local.name_prefix}-auth-key"
  target_key_id = aws_kms_key.auth.key_id
}

# Add KMS permissions to the Lambda role
resource "aws_iam_role_policy" "lambda_kms" {
  name = "${local.name_prefix}-lambda-kms"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSEncryptDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ]
        Resource = aws_kms_key.auth.arn
      }
    ]
  })
}
