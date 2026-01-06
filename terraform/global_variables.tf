variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "homebox"
}

variable "repository_owner" {
  description = "GitHub username of the repository owner"
  type        = string
  default     = "kamorion"
}

variable "region" {
  description = "AWS region where resources will be deployed"
  type        = string
  default     = "eu-west-3"
}

variable "aws_profile" {
  description = "AWS profile to ovveride default authentication"
  type        = string
  default     = ""
}

# Multi-account AWS profiles
variable "aws_profile_management" {
  description = "AWS profile for management account"
  type        = string
  default     = "homebox-management/AdministratorAccess"
}

variable "aws_profile_network" {
  description = "AWS profile for network account"
  type        = string
  default     = "homebox-network/AdministratorAccess"
}

variable "aws_profile_shared_services" {
  description = "AWS profile for shared-services account"
  type        = string
  default     = "homebox-shared-services/AdministratorAccess"
}

variable "aws_profile_state_backend" {
  description = "AWS profile for Terraform state backend operations (minimal permissions)"
  type        = string
  default     = "homebox-shared-services/TerraformStateBackendAccess"
}

variable "aws_profile_staging" {
  description = "AWS profile for staging environment"
  type        = string
  default     = "homebox-staging/AdministratorAccess"
}

variable "aws_profile_preprod" {
  description = "AWS profile for preprod environment"
  type        = string
  default     = "homebox-preprod/AdministratorAccess"
}

variable "aws_profile_production" {
  description = "AWS profile for production environment"
  type        = string
  default     = "homebox-production/AdministratorAccess"
}


variable "organization_role_name" {
  description = "Name of the IAM role created in child accounts for organization access"
  type        = string
  default     = "OrganizationAccountAccessRole"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "container_port_backend" {
  description = "Port on which the backend container listens"
  type        = number
  default     = 3000
}

variable "container_port_frontend" {
  description = "Port on which the frontend container listens"
  type        = number
  default     = 3000
}

variable "container_port_cms" {
  description = "Port on which the CMS container listens"
  type        = number
  default     = 1337
}

variable "container_port_teleoperateur" {
  description = "Port on which the Teleoperateur container listens (nginx)"
  type        = number
  default     = 80
}

variable "db_username" {
  description = "Username for the RDS database"
  type        = string
  default     = "dbadmin"
}

variable "db_password" {
  description = "Password for the RDS database (auto-generated if empty)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "use_custom_domain" {
  description = "Whether to use a custom domain"
  type        = bool
  default     = false
}

variable "route53_zone_name" {
  description = "The Route53 hosted zone name"
  type        = string
  default     = ""
}

variable "certificate_domain" {
  description = "Domain for SSL certificate"
  type        = string
  default     = ""
}

variable "email_domain" {
  description = "Domain to use for sending emails"
  type        = string
  default     = "yourdomain.com"
}

variable "use_nat_gateway" {
  description = "Use NAT Gateway (true) or NAT Instance (false)"
  type        = bool
  default     = true
}