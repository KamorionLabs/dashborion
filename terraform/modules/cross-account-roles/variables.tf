# ==============================================================================
# Cross-Account Dashboard Roles Module - Variables
# ==============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
}

variable "trusted_account_id" {
  description = "AWS account ID that will assume these roles (dashboard Lambda account)"
  type        = string
}

variable "target_account_id" {
  description = "AWS account ID where these roles are created (target environment)"
  type        = string
}

variable "environment" {
  description = "Environment name (staging, preprod, production)"
  type        = string
}

variable "enable_action_role" {
  description = "Whether to create the action role (for write operations)"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# Optional: Restrict read role permissions
variable "read_permissions" {
  description = "Custom read permissions. If not set, uses default comprehensive read permissions."
  type = list(object({
    sid       = string
    actions   = list(string)
    resources = list(string)
  }))
  default = null
}

# Optional: Restrict action role permissions
variable "action_permissions" {
  description = "Custom action permissions. If not set, uses default action permissions."
  type = list(object({
    sid       = string
    actions   = list(string)
    resources = list(string)
  }))
  default = null
}
