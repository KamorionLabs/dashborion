# ==============================================================================
# Dashborion Auth Infrastructure Module - Outputs
# ==============================================================================

output "permissions_table_name" {
  description = "Name of the permissions DynamoDB table"
  value       = aws_dynamodb_table.permissions.name
}

output "permissions_table_arn" {
  description = "ARN of the permissions DynamoDB table"
  value       = aws_dynamodb_table.permissions.arn
}

output "audit_table_name" {
  description = "Name of the audit log DynamoDB table"
  value       = aws_dynamodb_table.audit.name
}

output "audit_table_arn" {
  description = "ARN of the audit log DynamoDB table"
  value       = aws_dynamodb_table.audit.arn
}

output "kms_key_arn" {
  description = "ARN of the KMS key used for encryption (if enabled)"
  value       = local.kms_key_arn
}

output "dynamodb_access_policy_arn" {
  description = "ARN of the IAM policy for Lambda DynamoDB access"
  value       = aws_iam_policy.dynamodb_access.arn
}

output "admin_access_policy_arn" {
  description = "ARN of the IAM policy for admin DynamoDB access"
  value       = aws_iam_policy.admin_access.arn
}

output "permissions_table_gsi" {
  description = "Global Secondary Index name for project-environment queries"
  value       = "project-env-index"
}

output "audit_table_gsi" {
  description = "Global Secondary Index name for project-time queries"
  value       = "project-time-index"
}

output "device_codes_table_name" {
  description = "Name of the device codes DynamoDB table"
  value       = aws_dynamodb_table.device_codes.name
}

output "device_codes_table_arn" {
  description = "ARN of the device codes DynamoDB table"
  value       = aws_dynamodb_table.device_codes.arn
}

output "tokens_table_name" {
  description = "Name of the tokens DynamoDB table"
  value       = aws_dynamodb_table.tokens.name
}

output "tokens_table_arn" {
  description = "ARN of the tokens DynamoDB table"
  value       = aws_dynamodb_table.tokens.arn
}

output "tokens_table_gsi" {
  description = "Global Secondary Index name for user token queries"
  value       = "user-tokens-index"
}
