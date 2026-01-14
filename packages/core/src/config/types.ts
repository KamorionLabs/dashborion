/**
 * Main Dashborion configuration types
 *
 * These types define the configuration structure that is shared between:
 * - SST deployment (infrastructure)
 * - Frontend (React app)
 * - Backend (Python Lambda)
 */

/**
 * Authentication provider types
 */
export type AuthProvider = 'saml' | 'oidc' | 'none';

/**
 * SAML authentication configuration
 */
export interface SamlConfig {
  entityId: string;
  idpMetadataFile?: string;
}

/**
 * OIDC authentication configuration
 */
export interface OidcConfig {
  issuer: string;
  clientId: string;
  clientSecret?: string;
  scopes?: string[];
}

/**
 * Authentication configuration
 */
export interface AuthConfig {
  provider: AuthProvider;
  saml?: SamlConfig;
  oidc?: OidcConfig;
  sessionTtlSeconds?: number;
  cookieDomain?: string;
}

/**
 * Environment configuration
 */
export interface EnvironmentConfig {
  /** AWS Account ID */
  accountId: string;
  /** AWS Region */
  region: string;
  /** ECS cluster name (if using ECS) */
  clusterName?: string;
  /** EKS cluster name (if using EKS) */
  eksClusterName?: string;
  /** Kubernetes namespace (for EKS) */
  namespace?: string;
  /** Services to monitor (optional filter) */
  services?: string[];
  /** Infrastructure discovery config (ids/tags) */
  infrastructure?: InfrastructureConfig;
}

/**
 * Infrastructure resource configuration
 */
export interface InfrastructureResourceConfig {
  ids?: string[];
  tags?: Record<string, string>;
}

/**
 * Infrastructure discovery configuration
 */
export interface InfrastructureConfig {
  defaultTags?: Record<string, string>;
  domainConfig?: {
    domains?: Record<string, string>;
    pattern?: string;
  };
  resources?: Record<string, InfrastructureResourceConfig>;
}

/**
 * Project configuration
 */
export interface ProjectConfig {
  /** Display name */
  displayName: string;
  /** Description */
  description?: string;
  /** Service naming (prefix template) */
  serviceNaming?: {
    prefix?: string;
    suffix?: string;
  };
  /** Environments */
  environments: Record<string, EnvironmentConfig>;
  /** IDP group mapping for access control */
  idpGroupMapping?: Record<string, string[]>;
}

/**
 * Cross-account IAM role configuration
 */
export interface CrossAccountRole {
  /** Role ARN for read-only operations */
  readRoleArn: string;
  /** Role ARN for actions (deploy, scale, etc.) - optional */
  actionRoleArn?: string;
}

/**
 * CI/CD provider type
 */
export type CiProviderType = 'codepipeline' | 'github_actions' | 'gitlab' | 'bitbucket' | 'argocd';

/**
 * CI/CD provider configuration
 */
export interface CiProviderConfig {
  type: CiProviderType;
  /** GitHub Actions specific */
  github?: {
    owner: string;
    repoPattern?: string;
    tokenSecretArn?: string;
  };
  /** GitLab specific */
  gitlab?: {
    url: string;
    tokenSecretArn?: string;
  };
  /** ArgoCD specific */
  argocd?: {
    apiUrl: string;
    tokenSecretArn?: string;
  };
}

/**
 * Orchestrator type
 */
export type OrchestratorType = 'ecs' | 'eks' | 'kubernetes';

/**
 * Orchestrator configuration
 */
export interface OrchestratorConfig {
  type: OrchestratorType;
  /** EKS specific config */
  eks?: {
    defaultNamespace?: string;
  };
}

/**
 * Naming patterns for resources
 */
export interface NamingPatterns {
  cluster?: string;
  service?: string;
  taskFamily?: string;
  buildPipeline?: string;
  deployPipeline?: string;
  logGroup?: string;
  secret?: string;
  ecrRepo?: string;
}

/**
 * Feature flags for enabling/disabling functionality
 */
export interface FeatureFlags {
  /** Enable ECS monitoring */
  ecs?: boolean;
  /** Enable EKS monitoring */
  eks?: boolean;
  /** Enable CI/CD pipelines */
  pipelines?: boolean;
  /** Enable infrastructure view (ALB, RDS, etc.) */
  infrastructure?: boolean;
  /** Enable events timeline */
  events?: boolean;
  /** Enable actions (deploy, scale, etc.) */
  actions?: boolean;
  /** Enable environment comparison view (source vs destination) */
  comparison?: boolean;
  /** Enable refresh/migration operations view */
  refresh?: boolean;
}

/**
 * Theme configuration
 */
export interface ThemeConfig {
  primaryColor?: string;
  logo?: string;
  favicon?: string;
  title?: string;
}

/**
 * Main Dashborion configuration
 *
 * This configuration is used by:
 * - SST to deploy infrastructure
 * - Frontend to configure the UI
 * - Backend to configure providers
 */
export interface DashborionConfig {
  /** Projects to monitor */
  projects: Record<string, ProjectConfig>;

  /** Cross-account roles indexed by account ID */
  crossAccountRoles: Record<string, CrossAccountRole>;

  /** Shared services account ID (where dashboard is deployed) */
  sharedServicesAccount?: string;

  /** Default AWS region */
  region?: string;

  /** CI/CD provider configuration */
  ciProvider?: CiProviderConfig;

  /** Container orchestrator configuration */
  orchestrator?: OrchestratorConfig;

  /** Resource naming patterns */
  namingPatterns?: NamingPatterns;

  /** Feature flags */
  features?: FeatureFlags;

  /** Theme customization */
  theme?: ThemeConfig;

  /** SSO portal URL (for console links) */
  ssoPortalUrl?: string;

  /** GitHub configuration (for commit links) */
  github?: {
    owner: string;
    defaultBranch?: string;
  };
}

/**
 * SST-specific deployment configuration
 * Extends the base config with deployment options
 */
export interface SstDeploymentConfig {
  /** Domain for the dashboard */
  domain: string;

  /** Authentication configuration */
  auth: AuthConfig;

  /** Path to IDP metadata file (for SAML) */
  idpMetadataPath?: string;

  /** ACM certificate ARN (in us-east-1 for CloudFront) */
  certificateArn?: string;

  /** Backend configuration */
  backend?: {
    codePath?: string;
    memorySize?: number;
    timeout?: number;
  };

  /** Auth Lambda@Edge configuration */
  authLambda?: {
    codePath?: string;
  };
}

/**
 * Full SST configuration (deployment + dashborion config)
 */
export interface FullSstConfig extends SstDeploymentConfig {
  /** Dashborion configuration */
  config: DashborionConfig;
}
