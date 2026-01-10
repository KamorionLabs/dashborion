/**
 * Configuration types and loading for Dashborion infrastructure
 */

// ==========================================================================
// Configuration Types
// ==========================================================================

/**
 * Naming convention configuration
 * Allows customizing resource names to match organizational standards
 */
export interface NamingConfig {
  /** Naming convention preset: "default" uses SST defaults, "custom" uses prefixes */
  convention?: "default" | "custom";
  /** Application name used in resource names */
  app?: string;
  /** Owner/team identifier (e.g., "ops", "digital") */
  owner?: string;
  /** Resource type prefixes (e.g., "fct" for Lambda, "ddb" for DynamoDB) */
  prefixes?: {
    lambda?: string;        // e.g., "fct"
    layer?: string;         // e.g., "lyr"
    role?: string;          // e.g., "iam"
    table?: string;         // e.g., "ddb"
    api?: string;           // e.g., "api"
    securityGroup?: string; // e.g., "nsg"
    bucket?: string;        // e.g., "s3"
  };
  /** Pattern templates (use {app}, {stage}, {role}, {owner}, {prefix} placeholders) */
  patterns?: {
    lambda?: string;      // Default: "{app}-{stage}-{role}"
    table?: string;       // Default: "{app}-{stage}-{role}"
    api?: string;         // Default: "{app}-{stage}-api"
  };
}

/**
 * Tags configuration - custom tags applied to all resources
 */
export interface TagsConfig {
  [key: string]: string;
}

/**
 * Managed mode configuration
 * References to existing resources created by Terraform/OpenTofu
 */
export interface ManagedConfig {
  /** Lambda configuration - reference existing IAM role and VPC settings */
  lambda?: {
    /** ARN of existing IAM role for Lambda functions */
    roleArn?: string;
    /** Security Group IDs for Lambda VPC configuration */
    securityGroupIds?: string[];
    /** Subnet IDs for Lambda VPC configuration */
    subnetIds?: string[];
  };
  /** Lambda@Edge configuration */
  lambdaEdge?: {
    /** ARN of existing IAM role for Lambda@Edge functions (must be in us-east-1) */
    roleArn?: string;
  };
  /** DynamoDB tables - reference existing tables instead of creating new ones */
  dynamodb?: {
    tokensTable?: string;
    deviceCodesTable?: string;
    usersTable?: string;
    groupsTable?: string;
    permissionsTable?: string;
    auditTable?: string;
  };
}

/**
 * Authentication configuration
 */
export interface AuthConfig {
  enabled?: boolean;
  provider?: "saml" | "oidc" | "simple" | "none";
  saml?: {
    entityId: string;
    idpMetadataFile?: string;
    idpMetadataUrl?: string;
    idpMetadataXml?: string;
    acsPath?: string;
    metadataPath?: string;
    signAuthnRequests?: boolean;
  };
  sessionTtlSeconds?: number;
  cookieDomain?: string;
  sessionEncryptionKey?: string;
  excludedPaths?: string[];
  requireMfaForProduction?: boolean;
  /** KMS key ARN for session encryption (optional - SST creates one if not specified) */
  kmsKeyArn?: string;
  /** Enable SigV4 IAM authentication for Identity Center users */
  enableSigv4Users?: boolean;
  /** Enable SigV4 IAM authentication for service roles (M2M) */
  enableSigv4Services?: boolean;
  /** Allowed AWS account IDs for SigV4 authentication */
  allowedAwsAccountIds?: string[];
}

/**
 * Frontend configuration (for managed mode)
 */
export interface FrontendConfig {
  s3Bucket?: string;
  s3BucketArn?: string;
  s3BucketDomainName?: string;
  cloudfrontDistributionId?: string;
  cloudfrontDomain?: string;
  certificateArn?: string;
  originAccessControlId?: string;
}

/**
 * API Gateway configuration
 */
export interface ApiGatewayConfig {
  id?: string;
  url?: string;
  domain?: string;
  route53ZoneId?: string;
  route53Profile?: string;
}

/**
 * Cross-account role configuration
 */
export interface CrossAccountRole {
  readRoleArn: string;
  actionRoleArn?: string;
}

/**
 * Project environment configuration
 */
export interface ProjectEnvironment {
  accountId: string;
  region?: string;
  services: string[];
  clusterName?: string;
  namespace?: string;
}

/**
 * Project configuration
 */
export interface ProjectConfig {
  displayName: string;
  environments: Record<string, ProjectEnvironment>;
  idpGroupMapping?: Record<string, any>;
}

/**
 * Main infrastructure configuration file
 */
export interface InfraConfig {
  mode: "standalone" | "semi-managed" | "managed";
  aws?: {
    region?: string;
    profile?: string;
  };
  naming?: NamingConfig;
  tags?: TagsConfig;
  managed?: ManagedConfig;
  auth?: AuthConfig;
  /** @deprecated Use managed.lambda.roleArn instead */
  lambda?: {
    roleArn?: string;
  };
  frontend?: FrontendConfig;
  apiGateway?: ApiGatewayConfig;
  crossAccountRoles?: Record<string, CrossAccountRole>;
  projects?: Record<string, ProjectConfig>;
}

// ==========================================================================
// Configuration Loading
// ==========================================================================

let cachedConfig: InfraConfig | null = null;

/**
 * Get config directory (supports external config via DASHBORION_CONFIG_DIR)
 */
export function getConfigDir(): string {
  return process.env.DASHBORION_CONFIG_DIR || process.cwd();
}

/**
 * Load infrastructure config (sync, cached)
 */
export function loadConfig(): InfraConfig {
  if (cachedConfig) {
    return cachedConfig;
  }

  const fs = require("fs");
  const path = require("path");

  const configDir = getConfigDir();
  const externalConfig = path.join(configDir, "infra.config.json");
  const localConfig = path.join(process.cwd(), "infra.config.json");
  const exampleConfig = path.join(process.cwd(), "infra.config.example.json");

  let config: InfraConfig;

  // Priority 1: External config directory
  if (process.env.DASHBORION_CONFIG_DIR && fs.existsSync(externalConfig)) {
    console.log(`Loading config from: ${externalConfig}`);
    config = JSON.parse(fs.readFileSync(externalConfig, "utf-8"));
  }
  // Priority 2: Local config (gitignored)
  else if (fs.existsSync(localConfig)) {
    console.log(`Loading config from: ${localConfig}`);
    config = JSON.parse(fs.readFileSync(localConfig, "utf-8"));
  }
  // Priority 3: Example config (for development)
  else if (fs.existsSync(exampleConfig)) {
    console.log(`Loading example config from: ${exampleConfig}`);
    config = JSON.parse(fs.readFileSync(exampleConfig, "utf-8"));
  }
  // Default: standalone mode
  else {
    console.log("No config found, using standalone mode");
    config = { mode: "standalone" };
  }

  cachedConfig = config;
  return config;
}

/**
 * Get effective Lambda role ARN (supports both old and new config format)
 */
export function getLambdaRoleArn(config: InfraConfig): string | undefined {
  return config.managed?.lambda?.roleArn || config.lambda?.roleArn;
}

/**
 * Check if we should use existing DynamoDB tables
 */
export function useExistingDynamoDB(config: InfraConfig): boolean {
  return config.mode === "managed" && !!config.managed?.dynamodb;
}

/**
 * Check if we should use existing Lambda role
 */
export function useExistingLambdaRole(config: InfraConfig): boolean {
  return config.mode === "managed" && !!getLambdaRoleArn(config);
}

/**
 * Get VPC configuration for Lambdas
 */
export function getLambdaVpcConfig(config: InfraConfig): { securityGroupIds: string[]; subnetIds: string[] } | undefined {
  if (config.managed?.lambda?.securityGroupIds && config.managed?.lambda?.subnetIds) {
    return {
      securityGroupIds: config.managed.lambda.securityGroupIds,
      subnetIds: config.managed.lambda.subnetIds,
    };
  }
  return undefined;
}
