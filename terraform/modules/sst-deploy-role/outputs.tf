# ==============================================================================
# SST Deployment Role Module - Outputs
# ==============================================================================

output "role_arn" {
  description = "ARN of the SST deployment role"
  value       = aws_iam_role.sst_deploy.arn
}

output "role_name" {
  description = "Name of the SST deployment role"
  value       = aws_iam_role.sst_deploy.name
}

output "role_id" {
  description = "ID of the SST deployment role"
  value       = aws_iam_role.sst_deploy.id
}

output "mode" {
  description = "Deployment mode this role is configured for"
  value       = var.mode
}
