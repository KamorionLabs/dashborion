# Variables specific to the dashboard stack

variable "domain_name" {
  description = "Domain name for the dashboard"
  type        = string
  default     = "dashboard.homebox.kamorion.cloud"
}

variable "environment_services" {
  description = "Map of environments to services to monitor (account IDs come from organizations remote state)"
  type = map(object({
    services = list(string)
  }))
  default = {
    staging = {
      services = ["backend", "frontend", "cms"]
    }
    preprod = {
      services = ["backend", "frontend", "cms"]
    }
    production = {
      services = ["backend", "frontend", "cms"]
    }
  }
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

variable "github_org" {
  description = "GitHub organization name (for commit URLs)"
  type        = string
  default     = "HOMEBOXDEV"
}
