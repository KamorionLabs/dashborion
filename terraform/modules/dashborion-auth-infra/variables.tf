# ==============================================================================
# Dashborion Auth Infrastructure Module - Variables
# ==============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "dashborion"
}

variable "environment" {
  description = "Environment name (e.g., production, staging)"
  type        = string
  default     = "production"
}

variable "permissions_table_name" {
  description = "Name for the permissions DynamoDB table"
  type        = string
  default     = null # Will use {project_name}-permissions if not specified
}

variable "audit_table_name" {
  description = "Name for the audit log DynamoDB table"
  type        = string
  default     = null # Will use {project_name}-audit if not specified
}

variable "device_codes_table_name" {
  description = "Name for the device codes DynamoDB table (CLI auth)"
  type        = string
  default     = null # Will use {project_name}-device-codes if not specified
}

variable "tokens_table_name" {
  description = "Name for the tokens DynamoDB table (CLI auth)"
  type        = string
  default     = null # Will use {project_name}-tokens if not specified
}

variable "audit_retention_days" {
  description = "Number of days to retain audit log entries (TTL)"
  type        = number
  default     = 90
}

variable "enable_point_in_time_recovery" {
  description = "Enable point-in-time recovery for DynamoDB tables"
  type        = bool
  default     = true
}

variable "enable_encryption" {
  description = "Enable server-side encryption with KMS"
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "ARN of KMS key for encryption (if null, creates a new key)"
  type        = string
  default     = null
}

variable "lambda_role_arns" {
  description = "List of Lambda role ARNs that need access to the tables"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
