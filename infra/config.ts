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
  services?: string[];
  clusterName?: string;
  namespace?: string;
  status?: string;
  /** Override cross-account read role for this environment */
  readRoleArn?: string;
  /** Override cross-account action role for this environment */
  actionRoleArn?: string;
}

/**
 * CI/CD provider configuration
 */
export interface CIProviderConfig {
  type: "codepipeline" | "github_actions" | "bitbucket" | "argocd" | "none";
  config?: Record<string, any>;
}

/**
 * Orchestrator configuration
 */
export interface OrchestratorConfig {
  type: "ecs" | "eks" | "argocd";
  config?: Record<string, any>;
}

/**
 * Feature flags for frontend
 */
export interface FeaturesConfig {
  pipelines?: boolean;
  [key: string]: boolean | undefined;
}

/**
 * Pipeline provider types
 */
export type PipelineProviderType = "codepipeline" | "azure-devops" | "github-actions" | "bitbucket" | "argocd" | "jenkins";

/**
 * Pipeline category - what the pipeline does
 */
export type PipelineCategory = "build" | "deploy" | "both";

/**
 * Base pipeline provider configuration
 */
export interface BasePipelineProvider {
  /** Provider type */
  type: PipelineProviderType;
  /** What this provider handles: build, deploy, or both */
  category: PipelineCategory;
  /** Services managed by this provider */
  services: string[];
  /** Display name for this provider in the UI */
  displayName?: string;
}

/**
 * AWS CodePipeline provider
 */
export interface CodePipelineProvider extends BasePipelineProvider {
  type: "codepipeline";
  /** AWS account ID where pipelines are located */
  accountId: string;
  /** AWS region */
  region?: string;
}

/**
 * Azure DevOps provider
 */
export interface AzureDevOpsProvider extends BasePipelineProvider {
  type: "azure-devops";
  /** Azure DevOps organization */
  organization: string;
  /** Azure DevOps project */
  project: string;
  /** Pipeline name pattern (use {service} placeholder) */
  pipelinePattern?: string;
}

/**
 * GitHub Actions provider
 */
export interface GitHubActionsProvider extends BasePipelineProvider {
  type: "github-actions";
  /** GitHub organization or user */
  owner: string;
  /** Repository name pattern (use {service} placeholder) */
  repoPattern?: string;
  /** Workflow file pattern */
  workflowPattern?: string;
}

/**
 * Bitbucket Pipelines provider
 */
export interface BitbucketProvider extends BasePipelineProvider {
  type: "bitbucket";
  /** Bitbucket workspace */
  workspace: string;
  /** Repository name pattern (use {service} placeholder) */
  repoPattern?: string;
}

/**
 * ArgoCD provider (for GitOps deployments)
 */
export interface ArgoCDProvider extends BasePipelineProvider {
  type: "argocd";
  /** ArgoCD server URL */
  url: string;
  /** ArgoCD application name pattern (use {service}, {env} placeholders) */
  appPattern?: string;
}

/**
 * Jenkins provider
 */
export interface JenkinsProvider extends BasePipelineProvider {
  type: "jenkins";
  /** Jenkins server URL */
  url: string;
  /** Job name pattern (use {service} placeholder) */
  jobPattern?: string;
}

/**
 * Union type for all pipeline providers
 */
export type PipelineProvider =
  | CodePipelineProvider
  | AzureDevOpsProvider
  | GitHubActionsProvider
  | BitbucketProvider
  | ArgoCDProvider
  | JenkinsProvider;

/**
 * Per-project pipelines configuration
 */
export interface ProjectPipelinesConfig {
  /** Enable/disable pipelines for this project */
  enabled: boolean;
  /** List of pipeline providers for this project */
  providers?: PipelineProvider[];
}

/**
 * Project configuration
 */
export interface ProjectConfig {
  displayName: string;
  environments: Record<string, ProjectEnvironment>;
  idpGroupMapping?: Record<string, any>;
  /** Per-project pipelines configuration */
  pipelines?: ProjectPipelinesConfig;
  /** Feature flags specific to this project */
  features?: FeaturesConfig;
}

/**
 * SSM Parameter Store configuration
 */
export interface SsmConfig {
  /** SSM parameter prefix (default: /dashborion/{stage}) */
  prefix?: string;
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
  /** CI/CD provider configuration */
  ciProvider?: CIProviderConfig;
  /** Container orchestrator configuration */
  orchestrator?: OrchestratorConfig;
  /** Feature flags for frontend */
  features?: FeaturesConfig;
  /** SSM Parameter Store configuration for large configs */
  ssm?: SsmConfig;
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

  // Load IdP metadata XML from file if specified
  if (config.auth?.saml?.idpMetadataFile && !config.auth.saml.idpMetadataXml) {
    const metadataPath = path.join(configDir, config.auth.saml.idpMetadataFile);
    if (fs.existsSync(metadataPath)) {
      config.auth.saml.idpMetadataXml = fs.readFileSync(metadataPath, "utf-8");
      console.log(`Loaded IdP metadata from: ${metadataPath} (${config.auth.saml.idpMetadataXml.length} chars)`);
    } else {
      console.warn(`Warning: IdP metadata file not found: ${metadataPath}`);
    }
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
