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
export interface AuthorizerOptions {
  name: string;
  ttl?: string;
  identitySources?: string[];
}

export function setupAuthorizer(
  api: sst.aws.ApiGatewayV2,
  authorizerLambda: sst.aws.Function,
  options: AuthorizerOptions
) {
  return api.addAuthorizer({
    name: options.name,
    lambda: {
      function: authorizerLambda.arn,
      ttl: options.ttl ?? "0 seconds",
      identitySources: options.identitySources ?? [],
    },
  });
}

/**
 * Route configuration for API Gateway
 */
export function setupRoutes(
  api: sst.aws.ApiGatewayV2,
  lambdas: LambdaFunctions,
  authorizers: {
    default: ReturnType<typeof api.addAuthorizer>;
    session: ReturnType<typeof api.addAuthorizer>;
  }
): void {
  const authOptions = {
    auth: {
      lambda: authorizers.default.id,
    },
  };

  const authSessionOptions = {
    auth: {
      lambda: authorizers.session.id,
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
  api.route("GET /api/auth/me", lambdas.auth.arn, authSessionOptions);
  api.route("GET /api/auth/whoami", lambdas.auth.arn, authSessionOptions);
  api.route("POST /api/auth/device/verify", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/token/refresh", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/token/revoke", lambdas.auth.arn, authOptions);
  api.route("POST /api/auth/token/issue", lambdas.auth.arn, authSessionOptions);

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
  api.route("GET /api/{project}/infrastructure/{env}/meta", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/cloudfront", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/alb", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/rds", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/redis", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/s3", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/workloads", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/efs", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/network", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/routing", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/enis", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/security-group/{sgId}", lambdas.infrastructure.arn, authOptions);
  api.route("GET /api/{project}/infrastructure/{env}/nodes", lambdas.infrastructure.arn, authOptions);
  api.route("POST /api/{project}/actions/rds/{env}/{action}", lambdas.infrastructure.arn, authOptions);
  api.route("POST /api/{project}/actions/cloudfront/{env}/invalidate", lambdas.infrastructure.arn, authOptions);

  // Pipelines routes
  api.route("GET /api/{project}/pipelines/build/{service}", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/{project}/pipelines/deploy/{service}/{env}", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/{project}/images/{service}", lambdas.pipelines.arn, authOptions);
  api.route("POST /api/{project}/actions/build/{service}", lambdas.pipelines.arn, authOptions);

  // Jenkins discovery and history routes (for Admin UI and CLI)
  api.route("GET /api/pipelines/jenkins/discover", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/pipelines/jenkins/job/{jobPath+}", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/pipelines/jenkins/history/{jobPath+}", lambdas.pipelines.arn, authOptions);
  api.route("GET /api/pipelines/jenkins/params/{jobPath+}", lambdas.pipelines.arn, authOptions);

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

  // Comparison routes (environment comparison)
  api.route("GET /api/{project}/comparison/config", lambdas.comparison.arn, authOptions);
  api.route("GET /api/{project}/comparison/{sourceEnv}/{destEnv}/summary", lambdas.comparison.arn, authOptions);
  api.route("POST /api/{project}/comparison/{sourceEnv}/{destEnv}/trigger", lambdas.comparison.arn, authOptions);
  api.route("GET /api/{project}/comparison/{sourceEnv}/{destEnv}/status", lambdas.comparison.arn, authOptions);
  api.route("GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}", lambdas.comparison.arn, authOptions);
  api.route("GET /api/{project}/comparison/{sourceEnv}/{destEnv}/{checkType}/history", lambdas.comparison.arn, authOptions);

  // ==========================================================================
  // Config Registry Routes (admin - manage projects, environments, clusters, accounts)
  // ==========================================================================

  // Global settings
  api.route("GET /api/config/settings", lambdas.configRegistry.arn, authOptions);
  api.route("PUT /api/config/settings", lambdas.configRegistry.arn, authOptions);

  // Projects
  api.route("GET /api/config/projects", lambdas.configRegistry.arn, authOptions);
  api.route("GET /api/config/projects/{projectId}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/projects", lambdas.configRegistry.arn, authOptions);
  api.route("PUT /api/config/projects/{projectId}", lambdas.configRegistry.arn, authOptions);
  api.route("DELETE /api/config/projects/{projectId}", lambdas.configRegistry.arn, authOptions);

  // Environments
  api.route("GET /api/config/projects/{projectId}/environments", lambdas.configRegistry.arn, authOptions);
  api.route("GET /api/config/projects/{projectId}/environments/{envId}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/projects/{projectId}/environments", lambdas.configRegistry.arn, authOptions);
  api.route("PUT /api/config/projects/{projectId}/environments/{envId}", lambdas.configRegistry.arn, authOptions);
  api.route("DELETE /api/config/projects/{projectId}/environments/{envId}", lambdas.configRegistry.arn, authOptions);
  api.route("PATCH /api/config/projects/{projectId}/environments/{envId}/checkers", lambdas.configRegistry.arn, authOptions);

  // Clusters
  api.route("GET /api/config/clusters", lambdas.configRegistry.arn, authOptions);
  api.route("GET /api/config/clusters/{clusterId}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/clusters", lambdas.configRegistry.arn, authOptions);
  api.route("PUT /api/config/clusters/{clusterId}", lambdas.configRegistry.arn, authOptions);
  api.route("DELETE /api/config/clusters/{clusterId}", lambdas.configRegistry.arn, authOptions);

  // AWS Accounts (named aws_accounts for future multi-cloud support)
  api.route("GET /api/config/aws-accounts", lambdas.configRegistry.arn, authOptions);
  api.route("GET /api/config/aws-accounts/{accountId}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/aws-accounts", lambdas.configRegistry.arn, authOptions);
  api.route("PUT /api/config/aws-accounts/{accountId}", lambdas.configRegistry.arn, authOptions);
  api.route("DELETE /api/config/aws-accounts/{accountId}", lambdas.configRegistry.arn, authOptions);

  // CI Providers (Jenkins, ArgoCD, etc.)
  api.route("GET /api/config/ci-providers", lambdas.configRegistry.arn, authOptions);
  api.route("GET /api/config/ci-providers/{providerId}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/ci-providers", lambdas.configRegistry.arn, authOptions);
  api.route("PUT /api/config/ci-providers/{providerId}", lambdas.configRegistry.arn, authOptions);
  api.route("DELETE /api/config/ci-providers/{providerId}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/ci-providers/test", lambdas.configRegistry.arn, authOptions);  // Test before save
  api.route("POST /api/config/ci-providers/{providerId}/test", lambdas.configRegistry.arn, authOptions);

  // Import/Export/Validation
  api.route("GET /api/config/export", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/import", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/validate", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/migrate-from-json", lambdas.configRegistry.arn, authOptions);

  // Resolution (for terraform-aws-ops integration)
  api.route("GET /api/config/resolve/{projectId}/{envId}", lambdas.configRegistry.arn, authOptions);

  // Frontend config (full merged config for React app)
  api.route("GET /api/config/full", lambdas.configRegistry.arn, authOptions);

  // Secrets Management (CI/CD provider tokens stored in Secrets Manager)
  api.route("GET /api/config/secrets/{secretType}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/secrets/{secretType}", lambdas.configRegistry.arn, authOptions);
  api.route("DELETE /api/config/secrets/{secretType}", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/secrets/test-connection", lambdas.configRegistry.arn, authOptions);
  api.route("POST /api/config/secrets/discover", lambdas.configRegistry.arn, authOptions);

  // ==========================================================================
  // Discovery Routes (AWS resource discovery for Admin UI)
  // ==========================================================================

  // Test role directly (for form validation before save)
  api.route("GET /api/config/discovery/test-role", lambdas.discovery.arn, authOptions);

  // Test connection using saved config (legacy)
  api.route("GET /api/config/discovery/{accountId}/test", lambdas.discovery.arn, authOptions);

  // Resource discovery by type
  api.route("GET /api/config/discovery/{accountId}/{resourceType}", lambdas.discovery.arn, authOptions);
}
