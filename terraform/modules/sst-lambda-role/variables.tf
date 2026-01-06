# ==============================================================================
# SST Lambda Role Module - Variables
# ==============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "dashborion"
}

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"
}

variable "cross_account_role_arns" {
  description = "List of cross-account role ARNs the Lambda can assume"
  type        = list(string)
  default     = []
}

variable "additional_policy_arns" {
  description = "Additional managed policy ARNs to attach to the role"
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
