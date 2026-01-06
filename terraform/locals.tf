# Local values for the dashboard stack

locals {
  # Stack-specific configurations
  stack_name  = "dashboard"
  name_prefix = "${var.project_name}-${local.stack_name}"

  # Merge common tags with stack-specific tags
  stack_tags = merge(
    local.common_tags,
    {
      Stack       = local.stack_name
      Environment = "shared-services"
    }
  )

  # Identity Center portal URL for SSO console links
  sso_portal_url = data.terraform_remote_state.organizations.outputs.identity_center_portal_url

  # Account IDs from organizations remote state
  account_ids = {
    staging    = data.terraform_remote_state.organizations.outputs.staging_account_id
    preprod    = data.terraform_remote_state.organizations.outputs.preprod_account_id
    production = data.terraform_remote_state.organizations.outputs.production_account_id
  }

  # Build environments map with account IDs from remote state
  environments = {
    for env, config in var.environment_services : env => {
      account_id   = local.account_ids[env]
      services     = config.services
      region       = var.region
      cluster_name = null
      namespace    = null
    }
  }

  # =============================================================================
  # PROVIDER CONFIGURATIONS (for modular Lambda handler)
  # =============================================================================

  # CI/CD Provider configuration
  ci_provider = {
    type = "codepipeline"
    config = {
      repo_pattern = "{project}-{service}"
    }
  }

  # Orchestrator configuration
  orchestrator = {
    type = "ecs"
    config = {}
  }

  # Naming pattern configuration
  naming_pattern = {
    cluster         = "{project}-{env}-cluster"
    service         = "{project}-{env}-{service}"
    task_family     = "{project}-{env}-{service}"
    build_pipeline  = "{project}-build-{service}"
    deploy_pipeline = "{project}-deploy-{service}-{env}"
    log_group       = "/ecs/{project}-{env}/{service}"
    secret          = "{project}/{env}/{service}"
    ecr_repo        = "{project}-{service}"
    db_identifier   = "{project}-{env}"
  }

  # =============================================================================
  # CROSS-ACCOUNT ROLES
  # =============================================================================

  # AWS Console URLs for different services
  aws_console_urls = {
    ecs_cluster  = "https://%s.console.aws.amazon.com/ecs/v2/clusters/%s/services?region=%s"
    ecs_service  = "https://%s.console.aws.amazon.com/ecs/v2/clusters/%s/services/%s?region=%s"
    cloudwatch   = "https://%s.console.aws.amazon.com/cloudwatch/home?region=%s#dashboards"
    codepipeline = "https://%s.console.aws.amazon.com/codesuite/codepipeline/pipelines/%s/view?region=%s"
    ecr          = "https://%s.console.aws.amazon.com/ecr/repositories/private/%s/%s?region=%s"
  }

  # Cross-account role ARNs for each environment (read-only)
  cross_account_roles = {
    for env, config in local.environments : env => "arn:aws:iam::${config.account_id}:role/${var.project_name}-dashboard-read-role"
  }

  # Cross-account role ARNs for actions (write operations)
  cross_account_action_roles = {
    for env, config in local.environments : env => "arn:aws:iam::${config.account_id}:role/${var.project_name}-dashboard-action-role"
  }
}
