# ==============================================================================
# SST Lambda Role Module - Outputs
# ==============================================================================

output "role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda.arn
}

output "role_name" {
  description = "Name of the Lambda execution role"
  value       = aws_iam_role.lambda.name
}

output "role_id" {
  description = "ID of the Lambda execution role"
  value       = aws_iam_role.lambda.id
}

# Output for infra.config.json
output "infra_config_lambda" {
  description = "Configuration object for infra.config.json lambda section"
  value = {
    roleArn = aws_iam_role.lambda.arn
  }
}
