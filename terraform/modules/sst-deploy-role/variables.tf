# ==============================================================================
# SST Deployment Role Module - Variables
# ==============================================================================

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "dashborion"
}

variable "mode" {
  description = "SST deployment mode: standalone, semi-managed, or managed"
  type        = string
  default     = "standalone"

  validation {
    condition     = contains(["standalone", "semi-managed", "managed"], var.mode)
    error_message = "Mode must be one of: standalone, semi-managed, managed"
  }
}

variable "trusted_principals" {
  description = "List of IAM principals (users, roles, accounts) that can assume this role"
  type        = list(string)
  default     = []
}

variable "trusted_services" {
  description = "List of AWS services that can assume this role (e.g., codebuild.amazonaws.com)"
  type        = list(string)
  default     = []
}

variable "lambda_role_arn" {
  description = "ARN of the Lambda execution role (required for semi-managed and managed modes to grant PassRole)"
  type        = string
  default     = null
}

variable "s3_bucket_arn" {
  description = "ARN of the existing S3 bucket (required for managed mode)"
  type        = string
  default     = null
}

variable "cloudfront_distribution_arn" {
  description = "ARN of the existing CloudFront distribution (required for managed mode)"
  type        = string
  default     = null
}

variable "state_bucket_name" {
  description = "S3 bucket name for SST/Pulumi state storage"
  type        = string
  default     = null
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}
