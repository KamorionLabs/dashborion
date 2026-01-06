# ==============================================================================
# Cross-Account Dashboard Roles Module - Outputs
# ==============================================================================

output "read_role_arn" {
  description = "ARN of the read role for this environment"
  value       = aws_iam_role.dashboard_read.arn
}

output "read_role_name" {
  description = "Name of the read role"
  value       = aws_iam_role.dashboard_read.name
}

output "action_role_arn" {
  description = "ARN of the action role for this environment (null if not created)"
  value       = var.enable_action_role ? aws_iam_role.dashboard_action[0].arn : null
}

output "action_role_name" {
  description = "Name of the action role (null if not created)"
  value       = var.enable_action_role ? aws_iam_role.dashboard_action[0].name : null
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "target_account_id" {
  description = "Target AWS account ID"
  value       = var.target_account_id
}

# Output suitable for infra.config.json crossAccountRoles format
output "cross_account_config" {
  description = "Configuration object for infra.config.json crossAccountRoles"
  value = {
    accountId     = var.target_account_id
    readRoleArn   = aws_iam_role.dashboard_read.arn
    actionRoleArn = var.enable_action_role ? aws_iam_role.dashboard_action[0].arn : null
  }
}
