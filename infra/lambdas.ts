/**
 * Lambda functions for Dashborion API
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig, getLambdaRoleArn, getLambdaVpcConfig, useExistingLambdaRole } from "./config";
import { NamingHelper } from "./naming";
import { TagsHelper } from "./tags";
import { DynamoDBTables, getLinkableResources, getAllTableArns } from "./dynamodb";
import { KmsKeyRef, getKmsPermissions } from "./kms";

/**
 * Lambda function references
 */
export interface LambdaFunctions {
  authorizer: sst.aws.Function;
  health: sst.aws.Function;
  auth: sst.aws.Function;
  saml: sst.aws.Function;
  services: sst.aws.Function;
  infrastructure: sst.aws.Function;
  pipelines: sst.aws.Function;
  events: sst.aws.Function;
  admin: sst.aws.Function;
  comparison: sst.aws.Function;
  configRegistry: sst.aws.Function;
  discovery: sst.aws.Function;
}

/**
 * Common environment variables for all Lambdas
 */
export interface LambdaEnvVars {
  AWS_REGION_DEFAULT: string;
  AWS_ACCOUNT_ID?: string;
  CORS_ORIGINS: string;
  AUTH_PROVIDER: string;
  CI_PROVIDER: string;
  ORCHESTRATOR: string;
  FEATURES: string;
  COMPARISON: string;
  TOKENS_TABLE_NAME: $util.Output<string> | string;
  DEVICE_CODES_TABLE_NAME: $util.Output<string> | string;
  USERS_TABLE_NAME: $util.Output<string> | string;
  GROUPS_TABLE_NAME: $util.Output<string> | string;
  PERMISSIONS_TABLE_NAME: $util.Output<string> | string;
  AUDIT_TABLE_NAME: $util.Output<string> | string;
  CONFIG_TABLE_NAME: $util.Output<string> | string;
  CACHE_TABLE_NAME: $util.Output<string> | string;
  PYTHONPATH: string;
  // Ops Dashboard integration (Step Functions)
  OPS_DASHBOARD_TABLE?: string;
  // Auth security
  KMS_KEY_ARN?: $util.Output<string> | string;
  COOKIE_DOMAIN?: string;
  ALLOWED_AWS_ACCOUNT_IDS?: string;
  ENABLE_SIGV4_USERS?: string;
  ENABLE_SIGV4_SERVICES?: string;
}

/**
 * Build common environment variables
 *
 * Configuration is stored in DynamoDB Config Registry (CONFIG_TABLE_NAME).
 */
export function buildLambdaEnv(
  config: InfraConfig,
  tables: DynamoDBTables,
  frontendDomain: string,
  kmsKey?: KmsKeyRef
): LambdaEnvVars {
  // Build allowed account IDs from projects and cross-account roles
  const allowedAccountIds = new Set<string>();
  if (config.auth?.allowedAwsAccountIds) {
    config.auth.allowedAwsAccountIds.forEach(id => allowedAccountIds.add(id));
  }
  // Also add account IDs from projects
  if (config.projects) {
    for (const project of Object.values(config.projects)) {
      if (typeof project !== "object" || project === null) continue;
      for (const env of Object.values(project.environments || {})) {
        if (typeof env !== "object" || env === null) continue;
        if (env.accountId) allowedAccountIds.add(env.accountId);
      }
    }
  }

  // Build CI provider config (support "none" to disable pipelines)
  const ciProvider = {
    type: config.ciProvider?.type || "codepipeline",
    config: config.ciProvider?.config || {},
  };

  // Build orchestrator config
  const orchestrator = {
    type: config.orchestrator?.type || "ecs",
    config: config.orchestrator?.config || {},
  };

  const env: LambdaEnvVars = {
    AWS_REGION_DEFAULT: config.aws?.region || "eu-west-3",
    CORS_ORIGINS: `https://${frontendDomain}`,
    AUTH_PROVIDER: config.auth?.provider || "simple",
    CI_PROVIDER: JSON.stringify(ciProvider),
    ORCHESTRATOR: JSON.stringify(orchestrator),
    FEATURES: JSON.stringify(config.features || {}),
    COMPARISON: JSON.stringify(config.comparison || {}),
    TOKENS_TABLE_NAME: tables.tokens.name,
    DEVICE_CODES_TABLE_NAME: tables.deviceCodes.name,
    USERS_TABLE_NAME: tables.users.name,
    GROUPS_TABLE_NAME: tables.groups.name,
    PERMISSIONS_TABLE_NAME: tables.permissions.name,
    AUDIT_TABLE_NAME: tables.audit.name,
    CONFIG_TABLE_NAME: tables.config.name,
    CACHE_TABLE_NAME: tables.cache.name,
    PYTHONPATH: "/var/task/backend:/var/task",
  };

  // Add KMS key if provided
  if (kmsKey) {
    env.KMS_KEY_ARN = kmsKey.arn;
  }

  // Add auth-related environment variables
  if (config.auth?.cookieDomain) {
    env.COOKIE_DOMAIN = config.auth.cookieDomain;
  }
  if (allowedAccountIds.size > 0) {
    env.ALLOWED_AWS_ACCOUNT_IDS = Array.from(allowedAccountIds).join(',');
  }
  env.ENABLE_SIGV4_USERS = String(config.auth?.enableSigv4Users ?? true);
  env.ENABLE_SIGV4_SERVICES = String(config.auth?.enableSigv4Services ?? false);

  // Ops Dashboard integration (for EKS DynamoDB provider to trigger Step Functions)
  if (config.opsIntegration?.accountId) {
    env.AWS_ACCOUNT_ID = config.opsIntegration.accountId;
  }
  if (config.opsIntegration?.tableName) {
    env.OPS_DASHBOARD_TABLE = config.opsIntegration.tableName;
  }

  return env;
}

/**
 * Build cross-account role ARNs for assume role permission
 */
function getCrossAccountRoleArns(config: InfraConfig): string[] {
  const arns: string[] = [];
  if (config.crossAccountRoles) {
    for (const [accountId, role] of Object.entries(config.crossAccountRoles)) {
      if (accountId.startsWith("_") || typeof role !== "object" || role === null) continue;
      if (role.readRoleArn) arns.push(role.readRoleArn);
      if (role.actionRoleArn) arns.push(role.actionRoleArn);
    }
  }
  return arns;
}

/**
 * Create Lambda functions
 */
export function createLambdaFunctions(
  config: InfraConfig,
  naming: NamingHelper,
  tags: TagsHelper,
  tables: DynamoDBTables,
  frontendDomain: string,
  kmsKey?: KmsKeyRef
): LambdaFunctions {
  const useExistingRole = useExistingLambdaRole(config);
  const roleArn = getLambdaRoleArn(config);
  const vpcConfig = getLambdaVpcConfig(config);

  const env = buildLambdaEnv(config, tables, frontendDomain, kmsKey);
  const crossAccountRoleArns = getCrossAccountRoleArns(config);
  const tableArns = getAllTableArns(tables);
  const linkableResources = getLinkableResources(tables);

  // Common copyFiles for Python backend
  const commonCopyFiles = [{ from: "backend", to: "backend" }];

  // VPC configuration (if provided)
  // SST v3 requires privateSubnets instead of subnets
  const vpc = vpcConfig ? {
    securityGroups: vpcConfig.securityGroupIds,
    privateSubnets: vpcConfig.subnetIds,
  } : undefined;

  // Base function config
  const baseFunctionConfig = {
    runtime: "python3.12" as const,
    architecture: "arm64" as const,
    copyFiles: commonCopyFiles,
    ...(useExistingRole && roleArn ? { role: roleArn } : {}),
    ...(vpc ? { vpc } : {}),
  };

  // DynamoDB read permissions
  const dynamoReadPermissions = useExistingRole ? [] : [{
    actions: ["dynamodb:GetItem", "dynamodb:Query"],
    resources: tableArns,
  }];

  // DynamoDB full permissions
  const dynamoFullPermissions = useExistingRole ? [] : [{
    actions: ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:UpdateItem", "dynamodb:DeleteItem"],
    resources: tableArns,
  }];

  // Cross-account assume role permission
  const assumeRolePermission = useExistingRole || crossAccountRoleArns.length === 0 ? [] : [{
    actions: ["sts:AssumeRole"],
    resources: crossAccountRoleArns,
  }];

  // KMS permissions for auth encryption
  const kmsPermissions = useExistingRole || !kmsKey ? [] : getKmsPermissions(kmsKey);

  // Step Functions permissions for ops dashboard integration (EKS provider refresh)
  const sfnPermissions = useExistingRole || !config.opsIntegration?.accountId ? [] : [{
    actions: ["states:StartExecution", "states:DescribeExecution"],
    resources: [`arn:aws:states:${config.aws?.region || "eu-central-1"}:${config.opsIntegration.accountId}:stateMachine:ops-dashboard-*`],
  }];

  // --------------------------------------------------------------------------
  // Authorizer Lambda
  // --------------------------------------------------------------------------
  const authorizer = new sst.aws.Function("Authorizer", {
    ...baseFunctionConfig,
    handler: "backend/authorizer.handler",
    memory: "256 MB",
    timeout: "5 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoReadPermissions,
      ...kmsPermissions,
    ],
    transform: {
      function: {
        name: naming.lambda("authorizer"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Health Lambda (public)
  // --------------------------------------------------------------------------
  const health = new sst.aws.Function("HealthHandler", {
    ...baseFunctionConfig,
    handler: "backend/health/handler.handler",
    memory: "128 MB",
    timeout: "5 seconds",
    environment: {
      AWS_REGION_DEFAULT: config.aws?.region || "eu-west-3",
    },
    transform: {
      function: {
        name: naming.lambda("health"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Auth Lambda (Python - device flow, login, etc.)
  // --------------------------------------------------------------------------
  const auth = new sst.aws.Function("AuthHandler", {
    ...baseFunctionConfig,
    handler: "backend/auth/handler.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
      ...kmsPermissions,
    ],
    transform: {
      function: {
        name: naming.lambda("auth"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // SAML Lambda (TypeScript - SAML SSO authentication)
  // --------------------------------------------------------------------------
  const apiDomain = config.apiGateway?.domain ||
    (config.frontend?.cloudfrontDomain?.replace(/^dashboard\./, "dashboard-api.") || "");

  // Build SAML environment with KMS support
  const samlEnv: Record<string, any> = {
    API_DOMAIN: apiDomain,
    FRONTEND_DOMAIN: frontendDomain,
    IDP_METADATA_XML: config.auth?.saml?.idpMetadataXml || "",
    SP_ENTITY_ID: config.auth?.saml?.entityId || "dashborion",
    SIGN_AUTHN_REQUESTS: String(config.auth?.saml?.signAuthnRequests || false),
    SESSION_TTL_SECONDS: String(config.auth?.sessionTtlSeconds || 3600),
    TOKENS_TABLE_NAME: tables.tokens.name,
    USERS_TABLE_NAME: tables.users.name,
    GROUPS_TABLE_NAME: tables.groups.name,
    PERMISSIONS_TABLE_NAME: tables.permissions.name,
  };
  if (config.auth?.cookieDomain) {
    samlEnv.COOKIE_DOMAIN = config.auth.cookieDomain;
  }
  if (kmsKey) {
    samlEnv.KMS_KEY_ARN = kmsKey.arn;
  }

  const saml = new sst.aws.Function("SamlHandler", {
    runtime: "nodejs20.x",
    architecture: "arm64" as const,
    handler: "packages/auth/src/handlers/api-saml.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    ...(useExistingRole && roleArn ? { role: roleArn } : {}),
    ...(vpc ? { vpc } : {}),
    environment: samlEnv,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
      ...kmsPermissions,
    ],
    transform: {
      function: {
        name: naming.lambda("saml"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Services Lambda
  // --------------------------------------------------------------------------
  const services = new sst.aws.Function("ServicesHandler", {
    ...baseFunctionConfig,
    handler: "backend/services/handler.handler",
    memory: "512 MB",
    timeout: "120 seconds",  // Increased for Step Function refresh wait
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
      ...assumeRolePermission,
      ...sfnPermissions,
      ...(useExistingRole ? [] : [{
        actions: ["logs:GetLogEvents", "logs:FilterLogEvents", "logs:DescribeLogStreams", "logs:DescribeLogGroups"],
        resources: ["*"],
      }]),
    ],
    transform: {
      function: {
        name: naming.lambda("services"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Infrastructure Lambda
  // --------------------------------------------------------------------------
  const infrastructure = new sst.aws.Function("InfrastructureHandler", {
    ...baseFunctionConfig,
    handler: "backend/infrastructure/handler.handler",
    memory: "512 MB",
    timeout: "120 seconds",  // Increased for Step Function refresh wait
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
      ...assumeRolePermission,
      ...sfnPermissions,
    ],
    transform: {
      function: {
        name: naming.lambda("infrastructure"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Pipelines Lambda
  // --------------------------------------------------------------------------
  const pipelines = new sst.aws.Function("PipelinesHandler", {
    ...baseFunctionConfig,
    handler: "backend/pipelines/handler.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
      ...assumeRolePermission,
      // CodePipeline/ECR permissions (only when SST creates the role)
      ...(useExistingRole ? [] : [{
        actions: [
          "codepipeline:GetPipeline",
          "codepipeline:GetPipelineState",
          "codepipeline:GetPipelineExecution",
          "codepipeline:ListPipelineExecutions",
          "codepipeline:ListPipelines",
          "codepipeline:StartPipelineExecution",
        ],
        resources: ["*"],
      }]),
      ...(useExistingRole ? [] : [{
        actions: [
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
          "ecr:ListImages",
        ],
        resources: ["*"],
      }]),
      ...(useExistingRole ? [] : [{
        actions: [
          "codebuild:BatchGetBuilds",
          "codebuild:ListBuildsForProject",
        ],
        resources: ["*"],
      }]),
      // CloudWatch Logs for build logs
      ...(useExistingRole ? [] : [{
        actions: [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogStreams",
          "logs:DescribeLogGroups",
        ],
        resources: ["*"],
      }]),
    ],
    transform: {
      function: {
        name: naming.lambda("pipelines"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Events Lambda
  // --------------------------------------------------------------------------
  const events = new sst.aws.Function("EventsHandler", {
    ...baseFunctionConfig,
    handler: "backend/events/handler.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
      ...assumeRolePermission,
      // CloudTrail for enriching events
      ...(useExistingRole ? [] : [{
        actions: [
          "cloudtrail:LookupEvents",
        ],
        resources: ["*"],
      }]),
      // CodePipeline/ECR for pipeline events
      ...(useExistingRole ? [] : [{
        actions: [
          "codepipeline:GetPipeline",
          "codepipeline:GetPipelineState",
          "codepipeline:ListPipelineExecutions",
        ],
        resources: ["*"],
      }]),
      ...(useExistingRole ? [] : [{
        actions: [
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
        ],
        resources: ["*"],
      }]),
    ],
    transform: {
      function: {
        name: naming.lambda("events"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Admin Lambda
  // --------------------------------------------------------------------------
  const admin = new sst.aws.Function("AdminHandler", {
    ...baseFunctionConfig,
    handler: "backend/admin/handler.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
    ],
    transform: {
      function: {
        name: naming.lambda("admin"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Comparison Lambda (env comparison)
  // --------------------------------------------------------------------------
  const comparison = new sst.aws.Function("ComparisonHandler", {
    ...baseFunctionConfig,
    handler: "backend/comparison/handler.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoReadPermissions,
      ...assumeRolePermission,
    ],
    transform: {
      function: {
        name: naming.lambda("comparison"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Config Registry Lambda (projects, environments, clusters, accounts, settings)
  // --------------------------------------------------------------------------
  const configRegistry = new sst.aws.Function("ConfigRegistryHandler", {
    ...baseFunctionConfig,
    handler: "backend/config/handler.handler",
    memory: "256 MB",
    timeout: "30 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoFullPermissions,
    ],
    transform: {
      function: {
        name: naming.lambda("config-registry"),
        tags: tags.component("lambda"),
      },
    },
  });

  // --------------------------------------------------------------------------
  // Discovery Lambda (AWS resource discovery for Admin UI)
  // --------------------------------------------------------------------------
  const discovery = new sst.aws.Function("DiscoveryHandler", {
    ...baseFunctionConfig,
    handler: "backend/discovery/handler.handler",
    memory: "512 MB",
    timeout: "60 seconds",
    environment: env as any,
    ...(linkableResources.length > 0 ? { link: linkableResources } : {}),
    permissions: [
      ...dynamoReadPermissions,
      ...assumeRolePermission,
    ],
    transform: {
      function: {
        name: naming.lambda("discovery"),
        tags: tags.component("lambda"),
      },
    },
  });

  return {
    authorizer,
    health,
    auth,
    saml,
    services,
    infrastructure,
    pipelines,
    events,
    admin,
    comparison,
    configRegistry,
    discovery,
  };
}
