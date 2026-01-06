# Data sources for the dashboard stack

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Remote state for organizations (to get Route53 zone and account IDs)
data "terraform_remote_state" "organizations" {
  backend = "s3"
  config = {
    bucket  = local.state_bucket_name
    key     = "stacks/organizations/terraform.tfstate"
    region  = local.state_bucket_region
    profile = local.state_bucket_profile
  }
}
