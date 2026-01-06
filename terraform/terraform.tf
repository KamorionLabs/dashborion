terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    bucket         = "homebox-terraform-state"
    key            = "stacks/dashboard/terraform.tfstate"
    region         = "eu-west-3"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:eu-west-3:501994300510:key/14d15dcf-9560-4364-b507-459c56c919f3"
    dynamodb_table = "homebox-terraform-state-lock"
    profile        = "homebox-shared-services/TerraformStateBackendAccess"
  }
}
