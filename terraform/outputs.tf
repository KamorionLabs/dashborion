# ==============================================================================
# Dashboard Stack - Outputs
# ==============================================================================

output "dashboard_url" {
  description = "Dashboard URL"
  value       = "https://${var.domain_name}"
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.dashboard.id
}

output "cloudfront_domain_name" {
  description = "CloudFront domain name"
  value       = aws_cloudfront_distribution.dashboard.domain_name
}

output "api_gateway_url" {
  description = "API Gateway URL"
  value       = aws_apigatewayv2_api.dashboard.api_endpoint
}

output "frontend_bucket_name" {
  description = "Frontend S3 bucket name"
  value       = aws_s3_bucket.frontend.id
}

output "lambda_function_name" {
  description = "API Lambda function name"
  value       = aws_lambda_function.api.function_name
}

output "sso_saml_metadata_url" {
  description = "SAML metadata URL for Identity Center configuration"
  value       = "https://${var.domain_name}/saml/metadata.xml"
}

output "sso_saml_acs_url" {
  description = "SAML ACS URL for Identity Center configuration"
  value       = "https://${var.domain_name}/saml/acs"
}

output "deployment_instructions" {
  description = "Instructions for deploying the frontend"
  value       = <<-EOT

  Dashboard Deployment Instructions
  ==================================

  1. Build the frontend:
     cd stacks/20-dashboard/frontend
     npm install
     npm run build

  2. Deploy to S3:
     aws s3 sync dist/ s3://${aws_s3_bucket.frontend.id}/ --delete

  3. Invalidate CloudFront cache:
     aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.dashboard.id} --paths "/*"

  4. Configure Identity Center SAML Application:
     - Application ACS URL: https://${var.domain_name}/saml/acs
     - Application SAML audience: ${local.name_prefix}-sso
     - Download IDP metadata and save to: stacks/20-dashboard/idp-metadata/dashboard.xml

  Dashboard URL: https://${var.domain_name}

  EOT
}
