/**
 * API Gateway configuration for Dashborion
 * Supports custom domains with cross-account DNS validation
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig } from "./config";
import { NamingHelper } from "./naming";
import { TagsHelper } from "./tags";
import { LambdaFunctions } from "./lambdas";

/**
 * API Gateway output references
 */
export interface ApiGatewayOutput {
  api: sst.aws.ApiGatewayV2;
  url: $util.Output<string>;
  customDomain?: string;
  certificateArn?: $util.Output<string>;
}

/**
 * Determine the API domain from config
 */
export function getApiDomain(config: InfraConfig): string | null {
  if (config.apiGateway?.domain) {
    return config.apiGateway.domain;
  }
  // Derive from frontend domain: dashboard.x.y → dashboard-api.x.y
  if (config.frontend?.cloudfrontDomain) {
    return config.frontend.cloudfrontDomain.replace(/^dashboard\./, "dashboard-api.");
  }
  return null;
}

/**
 * Create API Gateway certificate for custom domain (cross-account DNS)
 */
export function createApiCertificate(
  config: InfraConfig,
  tags: TagsHelper,
  apiDomain: string,
  dnsProvider?: aws.Provider
): $util.Output<string> | undefined {
  if (!apiDomain || !config.apiGateway?.route53ZoneId || !dnsProvider) {
    return undefined;
  }

  // Create certificate in current account
  const apiCert = new aws.acm.Certificate("ApiCertificate", {
    domainName: apiDomain,
    validationMethod: "DNS",
    tags: tags.all(),
  });

  // Create DNS validation record in DNS account
  const apiCertValidation = new aws.route53.Record("ApiCertValidation", {
    zoneId: config.apiGateway.route53ZoneId,
    name: apiCert.domainValidationOptions[0].resourceRecordName,
    type: apiCert.domainValidationOptions[0].resourceRecordType,
    records: [apiCert.domainValidationOptions[0].resourceRecordValue],
    ttl: 300,
  }, { provider: dnsProvider });

  // Wait for certificate validation
  const apiCertValidated = new aws.acm.CertificateValidation("ApiCertValidated", {
    certificateArn: apiCert.arn,
    validationRecordFqdns: [apiCertValidation.fqdn],
  });

  return apiCertValidated.certificateArn;
}

/**
 * Create API Gateway with optional custom domain
 */
export function createApiGateway(
  config: InfraConfig,
  naming: NamingHelper,
  tags: TagsHelper,
  frontendDomain: string,
  apiDomain: string | null,
  certificateArn?: $util.Output<string>
): sst.aws.ApiGatewayV2 {
  return new sst.aws.ApiGatewayV2("DashborionApi", {
    // Custom domain with pre-validated certificate
    ...(apiDomain && certificateArn && {
      domain: {
        name: apiDomain,
        cert: certificateArn,
        dns: false, // We handle DNS ourselves
      },
    }),
    cors: {
      allowOrigins: [`https://${frontendDomain}`],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization", "x-sso-user-email"],
      allowCredentials: true,
    },
    transform: {
      api: {
        name: naming.api(),
        tags: tags.component("api-gateway"),
      },
    },
  });
}

/**
 * Create DNS A record for API custom domain
 */
export function createApiDnsRecord(
  config: InfraConfig,
  api: sst.aws.ApiGatewayV2,
  apiDomain: string,
  dnsProvider: aws.Provider
): void {
  if (!config.apiGateway?.route53ZoneId) return;

  new aws.route53.Record("ApiDomainRecord", {
    zoneId: config.apiGateway.route53ZoneId,
    name: apiDomain,
    type: "A",
    aliases: [{
      name: api.nodes.domainName!.domainNameConfiguration.apply(c => c.targetDomainName),
      zoneId: api.nodes.domainName!.domainNameConfiguration.apply(c => c.hostedZoneId),
      evaluateTargetHealth: false,
    }],
  }, { provider: dnsProvider });
}

/**
 * Setup API Gateway authorizer
 * Returns the authorizer for use in route configuration
 */
export function setupAuthorizer(
  api: sst.aws.ApiGatewayV2,
  authorizerLambda: sst.aws.Function
) {
  // NOTE: identitySources must be empty to support both:
  // - Bearer token in Authorization header (CLI device flow)
  // - SSO headers from Lambda@Edge (x-auth-user-email)
  return api.addAuthorizer({
    name: "DashborionAuth",
    lambda: {
      function: authorizerLambda.arn,
      ttl: "0 seconds", // Disable cache when using multiple auth methods
      identitySources: [],
    },
  });
}

/**
 * Route configuration for API Gateway
 */
export function setupRoutes(
  api: sst.aws.ApiGatewayV2,
  lambdas: LambdaFunctions,
  authorizer: ReturnType<typeof api.addAuthorizer>
): void {
  const authOptions = {
    auth: {
      lambda: authorizer.id,
    },
  };

  // ==========================================================================
  // Public Routes (no auth required)
  // ==========================================================================

  // Health check
  api.route("GET /api/health", lambdas.health.arn);

  // Auth - public endpoints (device flow, login)
  api.route("POST /api/auth/device/code", lambdas.auth.arn);
  api.route("POST /api/auth/device/token", lambdas.auth.arn);
  api.route("POST /api/auth/sso/exchange", lambdas.auth.arn);
  api.route("POST /api/auth/login", lambdas.auth.arn);

  // SAML SSO endpoints (public - handle authentication flow)
  // Uses dedicated TypeScript SAML handler with cookie-based sessions
  api.route("GET /api/auth/saml/login", lambdas.saml.arn);      // Initiates SAML flow -> redirect to IdP
  api.route("POST /api/auth/saml/acs", lambdas.saml.arn);       // ACS - receives SAML assertion from IdP
  api.route("GET /api/auth/saml/metadata", lambdas.saml.arn);   // SP metadata for IdP configuration

  // Admin init is public (for initial setup)
  api.route("POST /api/admin/init", lambdas.admin.arn);

  // ==========================================================================
  // Protected Routes (require auth)
  // ==========================================================================

  // Auth - protected endpoints
  api.route("GET /api/auth/me", lambdas.auth.arn, authOptions);
  api.route("GET /api/auth/whoami", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/device/verify", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/token/refresh", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/token/revoke", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/token/issue", lambdas.auth.arn, authOptions);

  // Projects and environments routes
  api.route("GET /api/projects", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/environments", lambdas.services.arn, authOptions);

  // Services routes
  api.route("GET /api/{project}/services", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/services/{env}", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/services/{env}/{service}", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/details/{env}/{service}", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/tasks/{env}/{service}/{taskId}", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/logs/{env}/{service}", lambdas.services.arn, authOptions);
  api.route("GET /api/{project}/metrics/{env}/{service}", lambdas.services.arn, authOptions);
  api.route("POST /api/{project}/actions/deploy/{env}/{service}/{action}", lambdas.services.arn, authOptions);

  // Infrastructure routes
  api.route("GET /api/{project}/infrastructure/{env}", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/routing", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/enis", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/security-group/{sgId}", lambdas.infrastructure.arn, authOptions);
  api.route("POST /api/{project}/actions/rds/{env}/{action}", lambdas.infrastructure.arn, authOptions);
  api.route("POST /api/{project}/actions/cloudfront/{env}/invalidate", lambdas.infrastructure.arn, authOptions);

  // Pipelines routes
  api.route("GET /api/{project}/pipelines/build/{service}", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/{project}/pipelines/deploy/{service}/{env}", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/{project}/images/{service}", lambdas.pipelines.arn, authOptions);
  api.route("POST /api/{project}/actions/build/{service}", lambdas.pipelines.arn, authOptions);

  // Events routes
  api.route("GET /api/{project}/events/{env}", lambdas.events.arn, authOptions);
  api.route("POST /api/{project}/events/{env}/enrich", lambdas.events.arn, authOptions);
  api.route("POST /api/{project}/events/{env}/task-diff", lambdas.events.arn, authOptions);

  // Admin routes (all protected, handler checks global admin)
  api.route("GET /api/admin/users", lambdas.admin.arn, authOptions);
  api.route("POST /api/admin/users", lambdas.admin.arn, authOptions);
  api.route("GET /api/admin/users/{email}", lambdas.admin.arn, authOptions);
  api.route("PUT /api/admin/users/{email}", lambdas.admin.arn, authOptions);
  api.route("DELETE /api/admin/users/{email}", lambdas.admin.arn, authOptions);
  api.route("GET /api/admin/groups", lambdas.admin.arn, authOptions);
  api.route("POST /api/admin/groups", lambdas.admin.arn, authOptions);
  api.route("GET /api/admin/groups/{name}", lambdas.admin.arn, authOptions);
  api.route("PUT /api/admin/groups/{name}", lambdas.admin.arn, authOptions);
  api.route("DELETE /api/admin/groups/{name}", lambdas.admin.arn, authOptions);
  api.route("GET /api/admin/permissions", lambdas.admin.arn, authOptions);
  api.route("POST /api/admin/permissions", lambdas.admin.arn, authOptions);
  api.route("DELETE /api/admin/permissions/{id}", lambdas.admin.arn, authOptions);
  api.route("GET /api/admin/audit", lambdas.admin.arn, authOptions);
}
