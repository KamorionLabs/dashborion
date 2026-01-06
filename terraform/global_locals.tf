locals {
  environment = terraform.workspace
  name        = "${var.project_name}-${local.environment}"

  # Repository names
  repository_backend  = "homebox-backend"
  repository_frontend = "homebox-front"
  repository_cms      = "homebox-strapi"

  # Environment-specific configurations
  is_production = local.environment == "production"
  is_staging    = local.environment == "staging"
  is_management = local.environment == "management"

  # Database configuration
  db_name = "${var.project_name}${local.environment}"

  # Availability zones configuration
  # Number of availability zones to use (minimum 2 for RDS subnet groups)
  az_count = 2 # AWS requires at least 2 AZs for DB subnet groups

  # Budget configuration
  budget_amount = local.is_production ? "500" : "100"

  # Feature flags
  enable_multi_az            = local.is_production
  enable_deletion_protection = local.is_production
  enable_backup              = true
  enable_monitoring          = true
  enable_macie               = local.is_production
  enable_inspector           = local.is_production
  enable_config              = local.is_production

  # Retention policies
  backup_retention_daily  = local.is_production ? 7 : 30
  backup_retention_weekly = local.is_production ? 5 : 90
  log_retention_days      = local.is_production ? 365 : 30

  # Common tags applied to all resources
  common_tags = {
    Name        = local.name
    Environment = local.environment
    Project     = var.project_name
    DevTeam     = "kanbios" # Default dev team, override with "tuesday" for teleoperateur resources
    ManagedBy   = "terraform"
    Workspace   = terraform.workspace
    Region      = var.region
    Owner       = var.repository_owner
  }

  # Terraform state backend configuration for remote state data sources
  state_bucket_name    = "${var.project_name}-terraform-state"
  state_bucket_region  = var.region
  state_bucket_profile = var.aws_profile_state_backend

  # Helper function for remote state configuration
  remote_state_config = {
    bucket  = local.state_bucket_name
    region  = local.state_bucket_region
    profile = local.state_bucket_profile
  }

  # Frontend domains per country configuration
  # Used by both 10-compute (ECS task env vars) and 11-cdn (CloudFront aliases + Route53)
  frontend_domains_config = {
    staging = {
      frontend_domain_fr = "fr.staging.homebox.kamorion.cloud"
      frontend_domain_eu = "eu.staging.homebox.kamorion.cloud"
      frontend_domain_de = "de.staging.homebox.kamorion.cloud"
      frontend_domain_es = "es.staging.homebox.kamorion.cloud"
      frontend_domain_ad = "ad.staging.homebox.kamorion.cloud"
      frontend_domain_pt = "pt.staging.homebox.kamorion.cloud"
      frontend_domain_ch = "ch.staging.homebox.kamorion.cloud"
      frontend_protocol  = "https"
      assets_domain      = "assets.staging.homebox.kamorion.cloud"
    }

    production = {
      frontend_domain_fr = "fr.homebox.kamorion.cloud"
      frontend_domain_eu = "eu.homebox.kamorion.cloud"
      frontend_domain_de = "de.homebox.kamorion.cloud"
      frontend_domain_es = "es.homebox.kamorion.cloud"
      frontend_domain_ad = "ad.homebox.kamorion.cloud"
      frontend_domain_pt = "pt.homebox.kamorion.cloud"
      frontend_domain_ch = "ch.homebox.kamorion.cloud"
      frontend_protocol  = "https"
      assets_domain      = "assets.homebox.kamorion.cloud"
    }

    default = {
      frontend_domain_fr = "fr.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_domain_eu = "eu.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_domain_de = "de.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_domain_es = "es.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_domain_ad = "ad.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_domain_pt = "pt.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_domain_ch = "ch.${terraform.workspace}.homebox.kamorion.cloud"
      frontend_protocol  = "https"
      assets_domain      = "assets.${terraform.workspace}.homebox.kamorion.cloud"
    }
  }

  # Select frontend domains based on current workspace
  current_frontend_domains = lookup(
    local.frontend_domains_config,
    terraform.workspace,
    local.frontend_domains_config.default
  )

  # Extract individual domain values for easy reference
  frontend_domain_fr = local.current_frontend_domains.frontend_domain_fr
  frontend_domain_eu = local.current_frontend_domains.frontend_domain_eu
  frontend_domain_de = local.current_frontend_domains.frontend_domain_de
  frontend_domain_es = local.current_frontend_domains.frontend_domain_es
  frontend_domain_ad = local.current_frontend_domains.frontend_domain_ad
  frontend_domain_pt = local.current_frontend_domains.frontend_domain_pt
  frontend_domain_ch = local.current_frontend_domains.frontend_domain_ch
  frontend_protocol  = local.current_frontend_domains.frontend_protocol
  assets_domain      = local.current_frontend_domains.assets_domain

  # List of all frontend domains (useful for CloudFront aliases and Route53 records)
  all_frontend_domains = [
    local.frontend_domain_fr,
    local.frontend_domain_eu,
    local.frontend_domain_de,
    local.frontend_domain_es,
    local.frontend_domain_ad,
    local.frontend_domain_pt,
    local.frontend_domain_ch,
    local.assets_domain
  ]

  # CMS domain configuration
  # Used by 10-compute (ECS task env vars and Route53)
  cms_domains_config = {
    staging = {
      cms_domain = "cms.staging.homebox.kamorion.cloud"
    }

    production = {
      cms_domain = "cms.homebox.kamorion.cloud"
    }

    default = {
      cms_domain = "cms.${terraform.workspace}.homebox.kamorion.cloud"
    }
  }

  # Select CMS domain based on current workspace
  current_cms_domain_config = lookup(
    local.cms_domains_config,
    terraform.workspace,
    local.cms_domains_config.default
  )

  # Extract CMS domain values
  cms_domain_name = local.current_cms_domain_config.cms_domain
  cms_url         = "https://${local.cms_domain_name}"

  # Assets URL (S3 base URL for CMS uploads via CloudFront)
  assets_url = "https://${local.assets_domain}"
}