# ==============================================================================
# CloudFront Distribution with SSO Auth
# ==============================================================================

# Origin Access Control for S3
resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name_prefix}-frontend-oac"
  description                       = "OAC for Dashboard Frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ACM Certificate for custom domain
resource "aws_acm_certificate" "dashboard" {
  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = local.stack_tags
}

# Route53 record for certificate validation (in management account)
resource "aws_route53_record" "cert_validation" {
  provider = aws.management

  for_each = {
    for dvo in aws_acm_certificate.dashboard.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  allow_overwrite = true
  name            = each.value.name
  records         = [each.value.record]
  ttl             = 60
  type            = each.value.type
  zone_id         = data.terraform_remote_state.organizations.outputs.route53_zone_id
}

# Certificate validation
resource "aws_acm_certificate_validation" "dashboard" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.dashboard.arn
  validation_record_fqdns = [for record in aws_route53_record.cert_validation : record.fqdn]
}

# CloudFront SSO Auth module (using existing module)
module "cloudfront_sso_auth" {
  source  = "KamorionLabs/cloudfront-sso-auth/aws"
  version = "0.3.2"

  sign_authn_requests = false  # AWS Identity Center has WantAuthnRequestsSigned=false

  name          = "${local.name_prefix}"
  saml_audience = "${local.name_prefix}-sso"

  # IDP metadata from Identity Center
  idp_metadata = file("${path.module}/idp-metadata/dashboard.xml")

  cloudfront_domains = [var.domain_name]

  log_retention_days = var.log_retention_days

  tags = local.stack_tags

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "dashboard" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${local.name_prefix} Distribution"
  default_root_object = "index.html"
  aliases             = [var.domain_name]
  price_class         = "PriceClass_100"

  # S3 Origin for static files
  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  # API Gateway Origin
  origin {
    domain_name = replace(aws_apigatewayv2_api.dashboard.api_endpoint, "https://", "")
    origin_id   = "api-gateway"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Default behavior (S3 static files) - protected by SSO
  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 3600
    max_ttl     = 86400

    # SSO Lambda@Edge
    lambda_function_association {
      event_type   = "viewer-request"
      lambda_arn   = module.cloudfront_sso_auth.lambda_protect_arn
      include_body = false
    }
  }

  # API behavior - protected by SSO
  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "api-gateway"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      headers      = ["x-sso-user-email"]  # Forward user email header for attribution
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    # SSO Lambda@Edge
    lambda_function_association {
      event_type   = "viewer-request"
      lambda_arn   = module.cloudfront_sso_auth.lambda_protect_arn
      include_body = true  # Allow POST body for action endpoints
    }
  }

  # SAML ACS endpoint
  ordered_cache_behavior {
    path_pattern           = "/saml/acs"
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = true
      cookies {
        forward = "all"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    lambda_function_association {
      event_type   = "viewer-request"
      lambda_arn   = module.cloudfront_sso_auth.lambda_acs_arn
      include_body = true
    }
  }

  # SAML metadata endpoint
  ordered_cache_behavior {
    path_pattern           = "/saml/metadata.xml"
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0

    lambda_function_association {
      event_type   = "viewer-request"
      lambda_arn   = module.cloudfront_sso_auth.lambda_metadata_arn
      include_body = false
    }
  }

  # SPA error handling
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  # Disable caching for 5xx errors (API errors should not be cached)
  custom_error_response {
    error_code            = 500
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 502
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 503
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 504
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.dashboard.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = local.stack_tags

  depends_on = [aws_acm_certificate_validation.dashboard]
}

# Route53 record for dashboard (in management account)
resource "aws_route53_record" "dashboard" {
  provider = aws.management

  zone_id = data.terraform_remote_state.organizations.outputs.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.dashboard.domain_name
    zone_id                = aws_cloudfront_distribution.dashboard.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "dashboard_ipv6" {
  provider = aws.management

  zone_id = data.terraform_remote_state.organizations.outputs.route53_zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.dashboard.domain_name
    zone_id                = aws_cloudfront_distribution.dashboard.hosted_zone_id
    evaluate_target_health = false
  }
}
