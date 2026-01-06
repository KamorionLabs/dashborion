# Provider configuration for dashboard stack
# This stack runs in shared-services account (not workspace-based)

provider "aws" {
  region  = var.region
  profile = var.aws_profile_shared_services

  default_tags {
    tags = local.stack_tags
  }
}

# US East 1 provider for CloudFront, Lambda@Edge, and ACM certificates
provider "aws" {
  alias   = "us_east_1"
  region  = "us-east-1"
  profile = var.aws_profile_shared_services

  default_tags {
    tags = local.stack_tags
  }
}

# Management account provider for Route53 (zone is in management account)
provider "aws" {
  alias   = "management"
  region  = var.region
  profile = var.aws_profile_management

  default_tags {
    tags = local.stack_tags
  }
}
