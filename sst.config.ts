/// <reference path="./.sst/platform/config.d.ts" />

/**
 * SST Configuration for Dashborion
 *
 * Three deployment modes:
 *
 * 1. STANDALONE (default): SST creates all resources
 *    - Frontend: SST creates S3 + CloudFront
 *    - Backend: SST creates Lambda + IAM role
 *    - Use for: development, testing, quick demos
 *    - Command: npx sst dev
 *
 * 2. SEMI-MANAGED: SST creates frontend, backend uses external role
 *    - Frontend: SST creates S3 + CloudFront
 *    - Backend: Lambda uses external IAM role (from Terraform)
 *    - Use for: production when only Lambda role is managed externally
 *    - Command: npx sst deploy --stage production
 *
 * 3. MANAGED: SST syncs to existing resources
 *    - Frontend: SST syncs to existing S3 bucket + invalidates CloudFront
 *    - Backend: Lambda uses external IAM role
 *    - Use for: production when all infra is managed by Terraform/CloudFormation
 *    - Command: npx sst deploy --stage production
 *
 * SST Deployment Role:
 *   - Use Terraform module sst-deploy-role to create a role for SST to assume
 *   - Configure via aws.profile in infra.config.json or AWS_PROFILE env var
 *
 * Configuration:
 *   - Create infra.config.json from infra.config.example.json
 *   - Set mode: "standalone", "semi-managed", or "managed"
 */

// Infrastructure configuration types
interface CrossAccountRole {
  accountId: string;
  readRoleArn: string;
  actionRoleArn: string;
}

interface SamlConfig {
  entityId: string;
  idpMetadataUrl: string;
  acsPath?: string;
  metadataPath?: string;
}

interface AuthConfig {
  enabled?: boolean;
  provider?: "saml" | "oidc";
  saml?: SamlConfig;
  sessionTtlSeconds?: number;
  cookieDomain?: string;
  encryptionKeyArn?: string;
  permissionsTableName?: string;
  auditTableName?: string;
  excludedPaths?: string[];
  requireMfaForProduction?: boolean;
}

interface InfraConfig {
  mode: "standalone" | "semi-managed" | "managed";
  aws?: {
    region?: string;
    profile?: string;
  };
  auth?: AuthConfig;
  lambda?: {
    roleArn?: string;
  };
  frontend?: {
    s3Bucket?: string;
    s3BucketArn?: string;
    s3BucketDomainName?: string;
    cloudfrontDistributionId?: string;
    cloudfrontDomain?: string;
    certificateArn?: string;  // ACM certificate ARN (us-east-1)
    originAccessControlId?: string;  // OAC ID for S3
  };
  apiGateway?: {
    id?: string;
    url?: string;
  };
  crossAccountRoles?: Record<string, CrossAccountRole>;
  projects?: Record<string, any>;  // Project configuration for multi-tenant
}

// Get config directory (supports external config via DASHBORION_CONFIG_DIR)
function getConfigDir(): string {
  return process.env.DASHBORION_CONFIG_DIR || process.cwd();
}

// Load infrastructure config (sync version for app() function)
// Config lookup order:
// 1. $DASHBORION_CONFIG_DIR/infra.config.json (external config)
// 2. ./infra.config.json (local, gitignored)
// 3. ./infra.config.example.json (fallback for dev)
function loadInfraConfig(): InfraConfig {
  const fs = require("fs");
  const path = require("path");

  const configDir = getConfigDir();
  const externalConfig = path.join(configDir, "infra.config.json");
  const localConfig = path.join(process.cwd(), "infra.config.json");
  const exampleConfig = path.join(process.cwd(), "infra.config.example.json");

  // Priority 1: External config directory
  if (process.env.DASHBORION_CONFIG_DIR && fs.existsSync(externalConfig)) {
    console.log(`Loading config from: ${externalConfig}`);
    const content = fs.readFileSync(externalConfig, "utf-8");
    return JSON.parse(content);
  }

  // Priority 2: Local config (gitignored)
  if (fs.existsSync(localConfig)) {
    console.log(`Loading config from: ${localConfig}`);
    const content = fs.readFileSync(localConfig, "utf-8");
    return JSON.parse(content);
  }

  // Priority 3: Example config (for development)
  if (fs.existsSync(exampleConfig)) {
    console.log(`Loading example config from: ${exampleConfig} (copy to infra.config.json for customization)`);
    const content = fs.readFileSync(exampleConfig, "utf-8");
    return JSON.parse(content);
  }

  // Default: standalone mode
  console.log("No config found, using standalone mode");
  return { mode: "standalone" };
}

// Get frontend config path (for copying to dist)
function getFrontendConfigPath(): string | null {
  const fs = require("fs");
  const path = require("path");

  const configDir = getConfigDir();
  const externalConfig = path.join(configDir, "frontend-config.json");
  const localConfig = path.join(process.cwd(), "frontend", "public", "config.json");

  // External config takes priority
  if (process.env.DASHBORION_CONFIG_DIR && fs.existsSync(externalConfig)) {
    return externalConfig;
  }

  // Fall back to local frontend config
  if (fs.existsSync(localConfig)) {
    return localConfig;
  }

  return null;
}

// Auth infrastructure outputs
interface AuthInfraOutput {
  permissionsTable: any;
  auditTable: any;
  tokensTable: any;
  deviceCodesTable: any;
  authProtectFunction: any;
  authAcsFunction: any;
  authMetadataFunction: any;
  apiAuthorizer: any;
  encryptionKey: any;
  jwtSecret: any;
  sessionSecret: any;
}

/**
 * Create authentication infrastructure
 * - KMS key for session encryption
 * - DynamoDB tables for permissions, audit, tokens, device_codes
 * - Lambda@Edge functions for CloudFront auth
 * - Lambda Authorizer for API Gateway
 */
async function createAuthInfrastructure(
  stage: string,
  config: InfraConfig,
  cloudfrontDomain: string
): Promise<AuthInfraOutput | null> {
  if (!config.auth?.enabled) {
    return null;
  }

  const authConfig = config.auth;

  // Create us-east-1 provider for Lambda@Edge (must be in us-east-1)
  const usEast1Provider = new aws.Provider("AwsUsEast1", {
    region: "us-east-1",
    ...(config.aws?.profile ? { profile: config.aws.profile } : {}),
  });

  // KMS key for session cookie encryption
  const encryptionKey = new aws.kms.Key("AuthEncryptionKey", {
    description: `Dashborion auth session encryption key (${stage})`,
    enableKeyRotation: true,
    tags: {
      Project: "dashborion",
      Stage: stage,
      Purpose: "session-encryption",
    },
  });

  new aws.kms.Alias("AuthEncryptionKeyAlias", {
    name: `alias/dashborion-${stage}-auth`,
    targetKeyId: encryptionKey.id,
  });

  // JWT secret for CLI tokens (stored in Secrets Manager)
  const jwtSecret = new aws.secretsmanager.Secret("JwtSecret", {
    name: `dashborion-${stage}-jwt-secret`,
    description: "JWT signing secret for Dashborion CLI tokens",
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // Generate random JWT secret value
  new aws.secretsmanager.SecretVersion("JwtSecretValue", {
    secretId: jwtSecret.id,
    secretString: $util.secret(
      require("crypto").randomBytes(32).toString("hex")
    ),
  });

  // Session encryption key for cookie encryption
  const sessionSecret = new aws.secretsmanager.Secret("SessionSecret", {
    name: `dashborion-${stage}-session-secret`,
    description: "Session encryption key for Dashborion cookies",
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // Generate random session secret value
  new aws.secretsmanager.SecretVersion("SessionSecretValue", {
    secretId: sessionSecret.id,
    secretString: $util.secret(
      require("crypto").randomBytes(32).toString("hex")
    ),
  });

  // DynamoDB table for permissions
  const permissionsTable = new aws.dynamodb.Table("PermissionsTable", {
    name: authConfig.permissionsTableName || `dashborion-${stage}-permissions`,
    billingMode: "PAY_PER_REQUEST",
    hashKey: "pk",
    rangeKey: "sk",
    attributes: [
      { name: "pk", type: "S" },
      { name: "sk", type: "S" },
      { name: "gsi1pk", type: "S" },
      { name: "gsi1sk", type: "S" },
    ],
    globalSecondaryIndexes: [
      {
        name: "project-env-index",
        hashKey: "gsi1pk",
        rangeKey: "gsi1sk",
        projectionType: "ALL",
      },
    ],
    pointInTimeRecovery: { enabled: true },
    serverSideEncryption: {
      enabled: true,
      kmsKeyArn: encryptionKey.arn,
    },
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // DynamoDB table for audit logs
  const auditTable = new aws.dynamodb.Table("AuditTable", {
    name: authConfig.auditTableName || `dashborion-${stage}-audit`,
    billingMode: "PAY_PER_REQUEST",
    hashKey: "pk",
    rangeKey: "sk",
    attributes: [
      { name: "pk", type: "S" },
      { name: "sk", type: "S" },
      { name: "gsi1pk", type: "S" },
      { name: "gsi1sk", type: "S" },
    ],
    globalSecondaryIndexes: [
      {
        name: "project-env-index",
        hashKey: "gsi1pk",
        rangeKey: "gsi1sk",
        projectionType: "ALL",
      },
    ],
    ttl: {
      attributeName: "ttl",
      enabled: true,
    },
    serverSideEncryption: {
      enabled: true,
      kmsKeyArn: encryptionKey.arn,
    },
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // DynamoDB table for tokens (CLI access/refresh tokens)
  const tokensTable = new aws.dynamodb.Table("TokensTable", {
    name: `dashborion-${stage}-tokens`,
    billingMode: "PAY_PER_REQUEST",
    hashKey: "pk",
    rangeKey: "sk",
    attributes: [
      { name: "pk", type: "S" },
      { name: "sk", type: "S" },
      { name: "gsi1pk", type: "S" },
      { name: "gsi1sk", type: "S" },
    ],
    globalSecondaryIndexes: [
      {
        name: "user-tokens-index",
        hashKey: "gsi1pk",
        rangeKey: "gsi1sk",
        projectionType: "ALL",
      },
    ],
    ttl: {
      attributeName: "ttl",
      enabled: true,
    },
    serverSideEncryption: {
      enabled: true,
      kmsKeyArn: encryptionKey.arn,
    },
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // DynamoDB table for device codes (CLI Device Flow)
  const deviceCodesTable = new aws.dynamodb.Table("DeviceCodesTable", {
    name: `dashborion-${stage}-device-codes`,
    billingMode: "PAY_PER_REQUEST",
    hashKey: "pk",
    rangeKey: "sk",
    attributes: [
      { name: "pk", type: "S" },
      { name: "sk", type: "S" },
    ],
    ttl: {
      attributeName: "ttl",
      enabled: true,
    },
    serverSideEncryption: {
      enabled: true,
      kmsKeyArn: encryptionKey.arn,
    },
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // Lambda@Edge IAM role (Lambda@Edge needs specific trust policy)
  const edgeRole = new aws.iam.Role("AuthEdgeRole", {
    name: `dashborion-${stage}-auth-edge-role`,
    assumeRolePolicy: JSON.stringify({
      Version: "2012-10-17",
      Statement: [
        {
          Effect: "Allow",
          Principal: {
            Service: ["lambda.amazonaws.com", "edgelambda.amazonaws.com"],
          },
          Action: "sts:AssumeRole",
        },
      ],
    }),
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // Edge role basic execution policy
  new aws.iam.RolePolicyAttachment("AuthEdgeRoleBasicExecution", {
    role: edgeRole.name,
    policyArn: "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
  });

  // Edge role KMS policy for decryption
  new aws.iam.RolePolicy("AuthEdgeRoleKmsPolicy", {
    role: edgeRole.name,
    policy: $interpolate`{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
          "Resource": "${encryptionKey.arn}"
        }
      ]
    }`,
  });

  // Build Lambda@Edge environment config
  const edgeEnv = {
    AUTH_SESSION_TTL: String(authConfig.sessionTtlSeconds || 3600),
    AUTH_COOKIE_DOMAIN: authConfig.cookieDomain || cloudfrontDomain,
    AUTH_EXCLUDED_PATHS: JSON.stringify(authConfig.excludedPaths || ["/health", "/api/health"]),
    // SAML config (note: Lambda@Edge env vars have limits, so we'll use SSM for metadata)
    AUTH_SAML_ENTITY_ID: authConfig.saml?.entityId || "dashborion",
    AUTH_SAML_ACS_PATH: authConfig.saml?.acsPath || "/saml/acs",
    AUTH_SAML_IDP_METADATA_URL: authConfig.saml?.idpMetadataUrl || "",
    // KMS key ID for encryption (region-independent)
    AUTH_KMS_KEY_ID: encryptionKey.id,
  };

  // Lambda@Edge: Protect (viewer-request)
  // Note: Lambda@Edge must be in us-east-1
  const path = require("path");
  const { execSync } = require("child_process");
  const authPath = path.join(process.cwd(), "auth");
  const authDistPath = path.join(authPath, "dist");

  // Build auth Lambda@Edge handlers
  console.log("Building auth Lambda@Edge handlers...");
  execSync("npm run build", {
    cwd: authPath,
    env: {
      ...process.env,
      DASHBORION_CONFIG_DIR: process.env.DASHBORION_CONFIG_DIR || process.cwd(),
    },
    stdio: "inherit",
  });

  const authProtectFunction = new aws.lambda.Function(
    "AuthProtect",
    {
      functionName: `dashborion-${stage}-auth-protect`,
      handler: "index.handler",
      runtime: "nodejs20.x",
      timeout: 5, // Lambda@Edge viewer-request max is 5 seconds
      memorySize: 128,
      role: edgeRole.arn,
      code: new $util.asset.FileArchive(path.join(authDistPath, "protect")),
      publish: true, // Lambda@Edge requires published versions
      tags: {
        Project: "dashborion",
        Stage: stage,
        Purpose: "auth-protect",
      },
    },
    { provider: usEast1Provider }
  );

  // Lambda@Edge: ACS (origin-request for /saml/acs)
  const authAcsFunction = new aws.lambda.Function(
    "AuthAcs",
    {
      functionName: `dashborion-${stage}-auth-acs`,
      handler: "index.handler",
      runtime: "nodejs20.x",
      timeout: 10, // Origin-request allows up to 30 seconds
      memorySize: 128, // Lambda@Edge max is 128MB
      role: edgeRole.arn,
      code: new $util.asset.FileArchive(path.join(authDistPath, "acs")),
      publish: true,
      tags: {
        Project: "dashborion",
        Stage: stage,
        Purpose: "auth-acs",
      },
    },
    { provider: usEast1Provider }
  );

  // Lambda@Edge: Metadata (viewer-request for /saml/metadata)
  const authMetadataFunction = new aws.lambda.Function(
    "AuthMetadata",
    {
      functionName: `dashborion-${stage}-auth-metadata`,
      handler: "index.handler",
      runtime: "nodejs20.x",
      timeout: 5,
      memorySize: 128,
      role: edgeRole.arn,
      code: new $util.asset.FileArchive(path.join(authDistPath, "metadata")),
      publish: true,
      tags: {
        Project: "dashborion",
        Stage: stage,
        Purpose: "auth-metadata",
      },
    },
    { provider: usEast1Provider }
  );

  // ==========================================================================
  // API Gateway Lambda Authorizer
  // Validates JWT tokens (CLI) and session cookies (Web)
  // ==========================================================================

  // IAM role for the authorizer Lambda
  const authorizerRole = new aws.iam.Role("ApiAuthorizerRole", {
    name: `dashborion-${stage}-api-authorizer-role`,
    assumeRolePolicy: JSON.stringify({
      Version: "2012-10-17",
      Statement: [
        {
          Effect: "Allow",
          Principal: { Service: "lambda.amazonaws.com" },
          Action: "sts:AssumeRole",
        },
      ],
    }),
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // Basic execution policy
  new aws.iam.RolePolicyAttachment("ApiAuthorizerRoleBasicExecution", {
    role: authorizerRole.name,
    policyArn: "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
  });

  // Authorizer DynamoDB and Secrets access policy
  new aws.iam.RolePolicy("ApiAuthorizerRolePolicy", {
    role: authorizerRole.name,
    policy: $interpolate`{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
            "dynamodb:GetItem",
            "dynamodb:Query"
          ],
          "Resource": [
            "${permissionsTable.arn}",
            "${permissionsTable.arn}/index/*",
            "${tokensTable.arn}",
            "${tokensTable.arn}/index/*"
          ]
        },
        {
          "Effect": "Allow",
          "Action": [
            "secretsmanager:GetSecretValue"
          ],
          "Resource": [
            "${jwtSecret.arn}",
            "${sessionSecret.arn}"
          ]
        },
        {
          "Effect": "Allow",
          "Action": [
            "kms:Decrypt"
          ],
          "Resource": "${encryptionKey.arn}"
        }
      ]
    }`,
  });

  // Lambda Authorizer function
  const apiAuthorizer = new aws.lambda.Function("ApiAuthorizer", {
    functionName: `dashborion-${stage}-api-authorizer`,
    handler: "authorizer.handler",
    runtime: "python3.11",
    timeout: 10,
    memorySize: 256,
    role: authorizerRole.arn,
    code: new $util.asset.FileArchive("backend"),
    environment: {
      variables: {
        STAGE: stage,
        PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
        SESSION_COOKIE_NAME: "dashborion_session",
        JWT_SECRET_ARN: jwtSecret.arn,
        SESSION_ENCRYPTION_KEY_ARN: sessionSecret.arn,
        PERMISSIONS_TABLE: permissionsTable.name,
        TOKENS_TABLE: tokensTable.name,
      },
    },
    tags: {
      Project: "dashborion",
      Stage: stage,
      Purpose: "api-authorizer",
    },
  });

  return {
    permissionsTable,
    auditTable,
    tokensTable,
    deviceCodesTable,
    authProtectFunction,
    authAcsFunction,
    authMetadataFunction,
    apiAuthorizer,
    encryptionKey,
    jwtSecret,
    sessionSecret,
  };
}

export default $config({
  app(input) {
    // Load config early to get AWS settings
    const config = loadInfraConfig();
    const awsRegion = config.aws?.region || process.env.AWS_REGION || "eu-west-3";
    const awsProfile = config.aws?.profile || process.env.AWS_PROFILE;

    const providers: Record<string, any> = {
      aws: {
        region: awsRegion,
        ...(awsProfile ? { profile: awsProfile } : {}),
      },
      "synced-folder": true,
    };

    return {
      name: "dashborion",
      removal: input?.stage === "production" ? "retain" : "remove",
      home: "aws",
      providers,
    };
  },

  async run() {
    const stage = $app.stage;
    const isProd = stage === "production";
    const config = loadInfraConfig();
    const awsRegion = config.aws?.region || process.env.AWS_REGION || "eu-west-3";

    console.log(`Deployment mode: ${config.mode}`);
    console.log(`AWS region: ${awsRegion}${config.aws?.profile ? `, profile: ${config.aws.profile}` : ""}`);

    switch (config.mode) {
      case "managed":
        return runManagedMode(stage, awsRegion, config);
      case "semi-managed":
        return runSemiManagedMode(stage, isProd, awsRegion, config);
      default:
        return runStandaloneMode(stage, isProd, awsRegion, config);
    }
  },
});

/**
 * STANDALONE MODE
 * SST creates all resources - ideal for dev/testing
 */
async function runStandaloneMode(stage: string, isProd: boolean, awsRegion: string, config: InfraConfig) {
  const customDomain = process.env.DASHBOARD_DOMAIN;
  const authEnabled = config.auth?.enabled ?? false;

  // Build cross-account role ARNs for Lambda environment
  const crossAccountRolesEnv = config.crossAccountRoles
    ? JSON.stringify(config.crossAccountRoles)
    : "{}";

  // Build auth infrastructure if enabled
  const authInfra = authEnabled
    ? await createAuthInfrastructure(stage, config, customDomain || "localhost")
    : null;

  // Backend environment variables
  const backendEnv: Record<string, string> = {
    STAGE: stage,
    PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
    AWS_REGION_DEFAULT: awsRegion,
    ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
    SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
    GITHUB_ORG: process.env.GITHUB_ORG || "",
    CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
  };

  // Add auth-related env vars if enabled
  if (authInfra) {
    backendEnv.AUTH_ENABLED = "true";
    backendEnv.PERMISSIONS_TABLE = authInfra.permissionsTable.name;
    backendEnv.AUDIT_TABLE = authInfra.auditTable.name;
    backendEnv.TOKENS_TABLE = authInfra.tokensTable.name;
    backendEnv.DEVICE_CODES_TABLE = authInfra.deviceCodesTable.name;
    backendEnv.JWT_SECRET_ARN = authInfra.jwtSecret.arn;
    backendEnv.SESSION_ENCRYPTION_KEY_ARN = authInfra.sessionSecret.arn;
  }

  // Backend permissions
  const backendPermissions = [
    "ecs:Describe*", "ecs:List*", "ecs:UpdateService",
    "eks:Describe*", "eks:List*",
    "logs:Describe*", "logs:FilterLogEvents", "logs:GetLogEvents",
    "codepipeline:Get*", "codepipeline:List*", "codepipeline:StartPipelineExecution",
    "codebuild:BatchGet*", "codebuild:List*",
    "ecr:Describe*", "ecr:List*", "ecr:GetAuthorizationToken",
    "elasticloadbalancing:Describe*",
    "rds:Describe*", "rds:StopDBInstance", "rds:StartDBInstance",
    "elasticache:Describe*",
    "cloudfront:Get*", "cloudfront:List*", "cloudfront:CreateInvalidation",
    "ec2:Describe*",
    "cloudtrail:LookupEvents",
    "secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret",
    "sts:AssumeRole",
    "s3:GetObject", "s3:ListBucket",
  ];

  // Add DynamoDB and Secrets permissions if auth is enabled
  if (authInfra) {
    backendPermissions.push(
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem"
    );
    // Note: secretsmanager:GetSecretValue is already included above
  }

  // Backend: API Gateway + Lambda (SST creates everything)
  const api = new sst.aws.ApiGatewayV2("DashborionApi", {
    cors: {
      allowOrigins: isProd
        ? [customDomain ? `https://${customDomain}` : "*"]
        : ["*"],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Auth-User-Id", "X-Auth-User-Email", "Cookie"],
      allowCredentials: true,
    },
  });

  const apiHandler = new sst.aws.Function("ApiHandler", {
    handler: "backend/handler.lambda_handler",
    runtime: "python3.11",
    timeout: "30 seconds",
    memory: "512 MB",
    environment: backendEnv,
    permissions: backendPermissions,
  });

  // If auth is enabled, create Lambda Authorizer for API Gateway
  if (authInfra) {
    // Permission for API Gateway to invoke the authorizer Lambda
    new aws.lambda.Permission("ApiAuthorizerPermission", {
      action: "lambda:InvokeFunction",
      function: authInfra.apiAuthorizer.name,
      principal: "apigateway.amazonaws.com",
      sourceArn: $interpolate`${api.nodes.api.executionArn}/*`,
    });

    // Create API Gateway HTTP API v2 Authorizer
    const httpAuthorizer = new aws.apigatewayv2.Authorizer("HttpAuthorizer", {
      apiId: api.nodes.api.id,
      authorizerType: "REQUEST",
      authorizerUri: authInfra.apiAuthorizer.invokeArn,
      authorizerPayloadFormatVersion: "2.0",
      authorizerResultTtlInSeconds: 300, // Cache auth results for 5 minutes
      identitySources: [
        "$request.header.Authorization",
        "$request.header.Cookie",
      ],
      name: `dashborion-${stage}-authorizer`,
    });

    // Permission for API Gateway to invoke backend Lambda
    new aws.lambda.Permission("ApiHandlerPermission", {
      action: "lambda:InvokeFunction",
      function: apiHandler.name,
      principal: "apigateway.amazonaws.com",
      sourceArn: $interpolate`${api.nodes.api.executionArn}/*`,
    });

    // Lambda integration for backend handler
    const backendIntegration = new aws.apigatewayv2.Integration("BackendIntegration", {
      apiId: api.nodes.api.id,
      integrationType: "AWS_PROXY",
      integrationUri: apiHandler.arn,
      integrationMethod: "POST",
      payloadFormatVersion: "2.0",
    });

    // Public routes (no authorization required)
    // These must be more specific to take precedence over wildcards
    const publicRoutes = [
      { path: "GET /health", key: "health" },
      { path: "GET /api/health", key: "apiHealth" },
      { path: "POST /api/auth/device/code", key: "deviceCode" },
      { path: "POST /api/auth/device/token", key: "deviceToken" },
      { path: "POST /api/auth/sso/exchange", key: "ssoExchange" },
    ];

    for (const route of publicRoutes) {
      new aws.apigatewayv2.Route(`PublicRoute-${route.key}`, {
        apiId: api.nodes.api.id,
        routeKey: route.path,
        target: $interpolate`integrations/${backendIntegration.id}`,
        authorizationType: "NONE",
      });
    }

    // Protected routes (authorization required)
    const protectedMethods = ["GET", "POST", "PUT", "DELETE"];
    for (const method of protectedMethods) {
      new aws.apigatewayv2.Route(`ProtectedRoute-${method}`, {
        apiId: api.nodes.api.id,
        routeKey: `${method} /api/{proxy+}`,
        target: $interpolate`integrations/${backendIntegration.id}`,
        authorizationType: "CUSTOM",
        authorizerId: httpAuthorizer.id,
      });
    }
  } else {
    // No auth - use simple SST routes
    api.route("GET /api/{proxy+}", apiHandler.arn);
    api.route("POST /api/{proxy+}", apiHandler.arn);
    api.route("PUT /api/{proxy+}", apiHandler.arn);
    api.route("DELETE /api/{proxy+}", apiHandler.arn);
    api.route("GET /health", apiHandler.arn);
  }

  let frontendUrl: string;

  // Frontend deployment depends on whether auth is enabled
  if (authEnabled && authInfra) {
    // With auth: Create custom CloudFront with Lambda@Edge
    const frontendInfra = await createFrontendWithAuth(
      stage,
      config,
      api.url,
      authInfra,
      customDomain
    );
    frontendUrl = frontendInfra.url;
  } else {
    // Without auth: Use SST StaticSite (simpler)
    const frontend = new sst.aws.StaticSite("DashborionFrontend", {
      path: "frontend",
      build: {
        command: "npm run build",
        output: "dist",
      },
      environment: {
        VITE_API_URL: api.url,
        VITE_STAGE: stage,
      },
      ...(customDomain && isProd ? {
        domain: {
          name: customDomain,
          dns: sst.aws.dns(),
        },
      } : {}),
    });
    frontendUrl = frontend.url;
  }

  const result: Record<string, any> = {
    mode: "standalone",
    stage,
    api: api.url,
    frontend: frontendUrl,
    crossAccountRoles: Object.keys(config.crossAccountRoles || {}),
  };

  if (authInfra) {
    result.auth = {
      enabled: true,
      permissionsTable: authInfra.permissionsTable.name,
      auditTable: authInfra.auditTable.name,
    };
  }

  return result;
}

/**
 * Create frontend S3 + CloudFront with Lambda@Edge auth
 */
async function createFrontendWithAuth(
  stage: string,
  config: InfraConfig,
  apiUrl: string,
  authInfra: AuthInfraOutput,
  customDomain?: string
): Promise<{ url: string; bucket: any; distribution: any }> {
  const fs = require("fs");
  const path = require("path");
  const frontendPath = path.join(process.cwd(), "frontend");
  const distPath = path.join(frontendPath, "dist");

  // Copy external frontend config if available
  const frontendConfigPath = getFrontendConfigPath();
  if (frontendConfigPath && frontendConfigPath !== path.join(frontendPath, "public", "config.json")) {
    console.log(`Copying frontend config from: ${frontendConfigPath}`);
    const configDir = getConfigDir();
    const destConfig = path.join(frontendPath, "public", "config.json");
    fs.copyFileSync(frontendConfigPath, destConfig);

    // Also copy any assets from the config directory (e.g., logo)
    const assetsDir = path.join(configDir, "assets");
    if (fs.existsSync(assetsDir)) {
      const assets = fs.readdirSync(assetsDir);
      for (const asset of assets) {
        fs.copyFileSync(
          path.join(assetsDir, asset),
          path.join(frontendPath, "public", asset)
        );
        console.log(`  Copied asset: ${asset}`);
      }
    }

    // Copy logo if exists at config dir root
    const logoPath = path.join(configDir, "kamorion-logo.png");
    if (fs.existsSync(logoPath)) {
      fs.copyFileSync(logoPath, path.join(frontendPath, "public", "kamorion-logo.png"));
      console.log("  Copied logo: kamorion-logo.png");
    }
  }

  // Build frontend
  console.log("Building frontend...");
  const { execSync } = require("child_process");
  execSync("npm run build", {
    cwd: frontendPath,
    env: {
      ...process.env,
      VITE_API_URL: apiUrl,
      VITE_STAGE: stage,
    },
    stdio: "inherit",
  });

  // S3 bucket for frontend assets
  const bucket = new aws.s3.Bucket("FrontendBucket", {
    bucket: `dashborion-${stage}-frontend-${Date.now()}`,
    forceDestroy: stage !== "production",
    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // Block public access (CloudFront will use OAC)
  new aws.s3.BucketPublicAccessBlock("FrontendBucketPublicAccessBlock", {
    bucket: bucket.id,
    blockPublicAcls: true,
    blockPublicPolicy: true,
    ignorePublicAcls: true,
    restrictPublicBuckets: true,
  });

  // Upload frontend assets
  const syncedFolder = new syncedfolder.S3BucketFolder("FrontendSync", {
    path: distPath,
    bucketName: bucket.id,
    acl: "private",
    managedObjects: true,
  });

  // Origin Access Control for CloudFront
  const oac = new aws.cloudfront.OriginAccessControl("FrontendOAC", {
    name: `dashborion-${stage}-frontend-oac`,
    description: "OAC for Dashborion frontend",
    originAccessControlOriginType: "s3",
    signingBehavior: "always",
    signingProtocol: "sigv4",
  });

  // CloudFront distribution with Lambda@Edge
  const distribution = new aws.cloudfront.Distribution("FrontendDistribution", {
    enabled: true,
    isIpv6Enabled: true,
    comment: `Dashborion ${stage} frontend`,
    defaultRootObject: "index.html",
    priceClass: "PriceClass_100", // US, Canada, Europe

    origins: [
      {
        domainName: bucket.bucketRegionalDomainName,
        originId: "S3Origin",
        originAccessControlId: oac.id,
      },
    ],

    defaultCacheBehavior: {
      targetOriginId: "S3Origin",
      viewerProtocolPolicy: "redirect-to-https",
      allowedMethods: ["GET", "HEAD", "OPTIONS"],
      cachedMethods: ["GET", "HEAD"],
      compress: true,

      forwardedValues: {
        queryString: false,
        cookies: { forward: "none" },
      },

      // Lambda@Edge associations for auth
      lambdaFunctionAssociations: [
        {
          eventType: "viewer-request",
          lambdaArn: authInfra.authProtectFunction.qualifiedArn,
          includeBody: false,
        },
      ],
    },

    // Custom error response for SPA routing
    customErrorResponses: [
      {
        errorCode: 403,
        responseCode: 200,
        responsePagePath: "/index.html",
        errorCachingMinTtl: 300,
      },
      {
        errorCode: 404,
        responseCode: 200,
        responsePagePath: "/index.html",
        errorCachingMinTtl: 300,
      },
    ],

    // SAML ACS endpoint behavior
    orderedCacheBehaviors: [
      {
        pathPattern: "/saml/acs",
        targetOriginId: "S3Origin",
        viewerProtocolPolicy: "https-only",
        allowedMethods: ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
        cachedMethods: ["GET", "HEAD"],
        compress: false,

        forwardedValues: {
          queryString: true,
          cookies: { forward: "all" },
        },

        lambdaFunctionAssociations: [
          {
            eventType: "viewer-request",
            lambdaArn: authInfra.authAcsFunction.qualifiedArn,
            includeBody: true,
          },
        ],
      },
      {
        pathPattern: "/saml/metadata",
        targetOriginId: "S3Origin",
        viewerProtocolPolicy: "https-only",
        allowedMethods: ["GET", "HEAD"],
        cachedMethods: ["GET", "HEAD"],
        compress: true,

        forwardedValues: {
          queryString: false,
          cookies: { forward: "none" },
        },

        lambdaFunctionAssociations: [
          {
            eventType: "viewer-request",
            lambdaArn: authInfra.authMetadataFunction.qualifiedArn,
            includeBody: false,
          },
        ],
      },
      {
        pathPattern: "/saml/logout",
        targetOriginId: "S3Origin",
        viewerProtocolPolicy: "https-only",
        allowedMethods: ["GET", "HEAD"],
        cachedMethods: ["GET", "HEAD"],
        compress: true,

        forwardedValues: {
          queryString: false,
          cookies: { forward: "all" },
        },

        lambdaFunctionAssociations: [
          {
            eventType: "viewer-request",
            lambdaArn: authInfra.authProtectFunction.qualifiedArn,
            includeBody: false,
          },
        ],
      },
    ],

    restrictions: {
      geoRestriction: {
        restrictionType: "none",
      },
    },

    viewerCertificate: customDomain
      ? {
          // Custom SSL certificate would be configured here
          cloudfrontDefaultCertificate: false,
          minimumProtocolVersion: "TLSv1.2_2021",
        }
      : {
          cloudfrontDefaultCertificate: true,
        },

    tags: {
      Project: "dashborion",
      Stage: stage,
    },
  });

  // S3 bucket policy for CloudFront OAC
  new aws.s3.BucketPolicy("FrontendBucketPolicy", {
    bucket: bucket.id,
    policy: $interpolate`{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "AllowCloudFrontServicePrincipal",
          "Effect": "Allow",
          "Principal": {
            "Service": "cloudfront.amazonaws.com"
          },
          "Action": "s3:GetObject",
          "Resource": "${bucket.arn}/*",
          "Condition": {
            "StringEquals": {
              "AWS:SourceArn": "${distribution.arn}"
            }
          }
        }
      ]
    }`,
  });

  return {
    url: $interpolate`https://${distribution.domainName}`,
    bucket,
    distribution,
  };
}

/**
 * SEMI-MANAGED MODE
 * SST creates frontend infrastructure, Lambda uses external role
 * - Frontend: SST creates S3 + CloudFront (with Lambda@Edge auth if enabled)
 * - Backend: Lambda uses external IAM role
 * - Auth: Lambda@Edge + DynamoDB (if enabled)
 */
async function runSemiManagedMode(stage: string, isProd: boolean, awsRegion: string, config: InfraConfig) {
  // Validate required config
  if (!config.lambda?.roleArn) {
    throw new Error("lambda.roleArn is required in semi-managed mode");
  }

  const customDomain = process.env.DASHBOARD_DOMAIN;
  const authEnabled = config.auth?.enabled ?? false;

  // Build cross-account role ARNs for Lambda environment
  const crossAccountRolesEnv = config.crossAccountRoles
    ? JSON.stringify(config.crossAccountRoles)
    : "{}";

  // Build auth infrastructure if enabled
  const authInfra = authEnabled
    ? await createAuthInfrastructure(stage, config, customDomain || "localhost")
    : null;

  // Backend environment variables
  const backendEnv: Record<string, string> = {
    STAGE: stage,
    PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
    AWS_REGION_DEFAULT: awsRegion,
    ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
    SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
    GITHUB_ORG: process.env.GITHUB_ORG || "",
    CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
  };

  // Add auth-related env vars if enabled
  if (authInfra) {
    backendEnv.AUTH_ENABLED = "true";
    backendEnv.PERMISSIONS_TABLE = authInfra.permissionsTable.name;
    backendEnv.AUDIT_TABLE = authInfra.auditTable.name;
    backendEnv.TOKENS_TABLE = authInfra.tokensTable.name;
    backendEnv.DEVICE_CODES_TABLE = authInfra.deviceCodesTable.name;
    backendEnv.JWT_SECRET_ARN = authInfra.jwtSecret.arn;
    backendEnv.SESSION_ENCRYPTION_KEY_ARN = authInfra.sessionSecret.arn;
  }

  // Backend: API Gateway + Lambda with external role
  const api = new sst.aws.ApiGatewayV2("DashborionApi", {
    cors: {
      allowOrigins: isProd
        ? [customDomain ? `https://${customDomain}` : "*"]
        : ["*"],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Auth-User-Id", "X-Auth-User-Email", "Cookie"],
      allowCredentials: authEnabled,
    },
  });

  const apiHandler = new sst.aws.Function("ApiHandler", {
    handler: "backend/handler.lambda_handler",
    runtime: "python3.11",
    timeout: "30 seconds",
    memory: "512 MB",
    role: config.lambda.roleArn,
    environment: backendEnv,
  });

  // If auth is enabled, create Lambda Authorizer for API Gateway
  if (authInfra) {
    // Permission for API Gateway to invoke the authorizer Lambda
    new aws.lambda.Permission("ApiAuthorizerPermission", {
      action: "lambda:InvokeFunction",
      function: authInfra.apiAuthorizer.name,
      principal: "apigateway.amazonaws.com",
      sourceArn: $interpolate`${api.nodes.api.executionArn}/*`,
    });

    // Create API Gateway HTTP API v2 Authorizer
    const httpAuthorizer = new aws.apigatewayv2.Authorizer("HttpAuthorizer", {
      apiId: api.nodes.api.id,
      authorizerType: "REQUEST",
      authorizerUri: authInfra.apiAuthorizer.invokeArn,
      authorizerPayloadFormatVersion: "2.0",
      authorizerResultTtlInSeconds: 300,
      identitySources: [
        "$request.header.Authorization",
        "$request.header.Cookie",
      ],
      name: `dashborion-${stage}-authorizer`,
    });

    // Permission for API Gateway to invoke backend Lambda
    new aws.lambda.Permission("ApiHandlerPermission", {
      action: "lambda:InvokeFunction",
      function: apiHandler.name,
      principal: "apigateway.amazonaws.com",
      sourceArn: $interpolate`${api.nodes.api.executionArn}/*`,
    });

    // Lambda integration for backend handler
    const backendIntegration = new aws.apigatewayv2.Integration("BackendIntegration", {
      apiId: api.nodes.api.id,
      integrationType: "AWS_PROXY",
      integrationUri: apiHandler.arn,
      integrationMethod: "POST",
      payloadFormatVersion: "2.0",
    });

    // Public routes (no authorization required)
    const publicRoutes = [
      { path: "GET /health", key: "health" },
      { path: "GET /api/health", key: "apiHealth" },
      { path: "POST /api/auth/device/code", key: "deviceCode" },
      { path: "POST /api/auth/device/token", key: "deviceToken" },
      { path: "POST /api/auth/sso/exchange", key: "ssoExchange" },
    ];

    for (const route of publicRoutes) {
      new aws.apigatewayv2.Route(`PublicRoute-${route.key}`, {
        apiId: api.nodes.api.id,
        routeKey: route.path,
        target: $interpolate`integrations/${backendIntegration.id}`,
        authorizationType: "NONE",
      });
    }

    // Protected routes (authorization required)
    const protectedMethods = ["GET", "POST", "PUT", "DELETE"];
    for (const method of protectedMethods) {
      new aws.apigatewayv2.Route(`ProtectedRoute-${method}`, {
        apiId: api.nodes.api.id,
        routeKey: `${method} /api/{proxy+}`,
        target: $interpolate`integrations/${backendIntegration.id}`,
        authorizationType: "CUSTOM",
        authorizerId: httpAuthorizer.id,
      });
    }
  } else {
    // No auth - use simple SST routes
    api.route("GET /api/{proxy+}", apiHandler.arn);
    api.route("POST /api/{proxy+}", apiHandler.arn);
    api.route("PUT /api/{proxy+}", apiHandler.arn);
    api.route("DELETE /api/{proxy+}", apiHandler.arn);
    api.route("GET /health", apiHandler.arn);
  }

  let frontendUrl: string;

  // Frontend deployment depends on whether auth is enabled
  if (authEnabled && authInfra) {
    // With auth: Create custom CloudFront with Lambda@Edge
    const frontendInfra = await createFrontendWithAuth(
      stage,
      config,
      api.url,
      authInfra,
      customDomain
    );
    frontendUrl = frontendInfra.url;
  } else {
    // Without auth: Use SST StaticSite (simpler)
    const frontend = new sst.aws.StaticSite("DashborionFrontend", {
      path: "frontend",
      build: {
        command: "npm run build",
        output: "dist",
      },
      environment: {
        VITE_API_URL: api.url,
        VITE_STAGE: stage,
      },
      ...(customDomain && isProd ? {
        domain: {
          name: customDomain,
          dns: sst.aws.dns(),
        },
      } : {}),
    });
    frontendUrl = frontend.url;
  }

  const result: Record<string, any> = {
    mode: "semi-managed",
    stage,
    api: api.url,
    frontend: frontendUrl,
    lambdaRole: config.lambda.roleArn,
    crossAccountRoles: Object.keys(config.crossAccountRoles || {}),
  };

  if (authInfra) {
    result.auth = {
      enabled: true,
      permissionsTable: authInfra.permissionsTable.name,
      auditTable: authInfra.auditTable.name,
    };
  }

  return result;
}

/**
 * MANAGED MODE
 * SST manages CloudFront, API Gateway, Lambda, and auth infrastructure
 * Uses existing S3 bucket and IAM role
 *
 * - Frontend: Syncs to existing S3 bucket
 * - CloudFront: Imported and managed by SST (updated origins, Lambda@Edge)
 * - API Gateway: Created by SST
 * - Lambda: Created by SST with external IAM role
 * - Auth: Lambda@Edge + DynamoDB (if enabled)
 */
async function runManagedMode(stage: string, awsRegion: string, config: InfraConfig) {
  // Validate required config
  if (!config.lambda?.roleArn) {
    throw new Error("lambda.roleArn is required in managed mode");
  }
  if (!config.frontend?.s3Bucket) {
    throw new Error("frontend.s3Bucket is required in managed mode");
  }
  if (!config.frontend?.cloudfrontDistributionId) {
    throw new Error("frontend.cloudfrontDistributionId is required in managed mode");
  }
  if (!config.frontend?.cloudfrontDomain) {
    throw new Error("frontend.cloudfrontDomain is required in managed mode");
  }

  const path = require("path");
  const { execSync } = require("child_process");

  // Build cross-account role ARNs for Lambda environment
  const crossAccountRolesEnv = config.crossAccountRoles
    ? JSON.stringify(config.crossAccountRoles)
    : "{}";

  const authEnabled = config.auth?.enabled ?? false;
  const cloudfrontDomain = config.frontend.cloudfrontDomain;

  // ==========================================================================
  // 1. Create API Gateway + Lambda
  // ==========================================================================
  const api = new sst.aws.ApiGatewayV2("DashborionApi", {
    cors: {
      allowOrigins: [`https://${cloudfrontDomain}`],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "Cookie"],
      allowCredentials: true,
    },
  });

  // Backend environment variables
  const backendEnv: Record<string, string> = {
    STAGE: stage,
    PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
    AWS_REGION_DEFAULT: awsRegion,
    ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
    SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
    GITHUB_ORG: process.env.GITHUB_ORG || "",
    CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
  };

  const apiHandler = new sst.aws.Function("ApiHandler", {
    handler: "backend/handler.lambda_handler",
    runtime: "python3.11",
    timeout: "30 seconds",
    memory: "512 MB",
    role: config.lambda.roleArn,
    environment: backendEnv,
  });

  api.route("GET /api/{proxy+}", apiHandler.arn);
  api.route("POST /api/{proxy+}", apiHandler.arn);
  api.route("PUT /api/{proxy+}", apiHandler.arn);
  api.route("DELETE /api/{proxy+}", apiHandler.arn);
  api.route("GET /health", apiHandler.arn);

  // ==========================================================================
  // 2. Create Auth Infrastructure (if enabled)
  // ==========================================================================
  let authInfra: AuthInfraOutput | null = null;
  if (authEnabled) {
    authInfra = await createAuthInfrastructure(stage, config, cloudfrontDomain);
  }

  // ==========================================================================
  // 3. Build Frontend
  // ==========================================================================
  const frontendPath = path.join(process.cwd(), "frontend");
  const distPath = path.join(frontendPath, "dist");

  console.log("Building frontend...");
  execSync("npm run build", {
    cwd: frontendPath,
    env: {
      ...process.env,
      // CloudFront proxies /api/* to API Gateway - use relative paths
      VITE_STAGE: stage,
    },
    stdio: "inherit",
  });

  // ==========================================================================
  // 4. Sync Frontend to existing S3 bucket
  // ==========================================================================
  const s3Bucket = config.frontend.s3Bucket;

  new syncedfolder.S3BucketFolder("FrontendSync", {
    path: distPath,
    bucketName: s3Bucket,
    acl: "private",
    managedObjects: true,
  });

  // ==========================================================================
  // 5. Create CloudFront Distribution (SST manages everything)
  // ==========================================================================
  const certificateArn = config.frontend.certificateArn;
  const s3BucketDomainName = config.frontend.s3BucketDomainName ||
    `${s3Bucket}.s3.${awsRegion}.amazonaws.com`;

  // Get API Gateway domain from URL (remove https:// and trailing /)
  const apiDomain = api.url.apply(url => url.replace("https://", "").replace(/\/$/, ""));

  // Create Origin Access Control for S3
  const oac = new aws.cloudfront.OriginAccessControl("FrontendOAC", {
    name: `dashborion-${stage}-frontend-oac`,
    description: "OAC for Dashborion frontend S3 bucket",
    originAccessControlOriginType: "s3",
    signingBehavior: "always",
    signingProtocol: "sigv4",
  });

  // Build Lambda@Edge associations for default behavior
  const defaultLambdaAssociations = authInfra ? [
    {
      eventType: "viewer-request",
      lambdaArn: authInfra.authProtectFunction.qualifiedArn,
      includeBody: false,
    },
  ] : [];

  // Build ordered cache behaviors
  const orderedCacheBehaviors: any[] = [
    // API behavior - proxy to API Gateway
    {
      pathPattern: "/api/*",
      targetOriginId: "api-gateway",
      viewerProtocolPolicy: "redirect-to-https",
      allowedMethods: ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      cachedMethods: ["GET", "HEAD"],
      compress: true,
      forwardedValues: {
        queryString: true,
        headers: authEnabled ? ["Authorization", "x-sso-user-email"] : ["Authorization"],
        cookies: { forward: authEnabled ? "all" : "none" },
      },
      minTtl: 0,
      defaultTtl: 0,
      maxTtl: 0,
      lambdaFunctionAssociations: authInfra ? [
        {
          eventType: "viewer-request",
          lambdaArn: authInfra.authProtectFunction.qualifiedArn,
          includeBody: true,
        },
      ] : [],
    },
  ];

  // Add SAML endpoints if auth is enabled
  if (authInfra) {
    orderedCacheBehaviors.push(
      // SAML ACS endpoint
      {
        pathPattern: config.auth?.saml?.acsPath || "/saml/acs",
        targetOriginId: "s3-frontend",
        viewerProtocolPolicy: "https-only",
        allowedMethods: ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
        cachedMethods: ["GET", "HEAD"],
        compress: false,
        forwardedValues: {
          queryString: true,
          cookies: { forward: "all" },
        },
        minTtl: 0,
        defaultTtl: 0,
        maxTtl: 0,
        lambdaFunctionAssociations: [
          {
            eventType: "viewer-request",
            lambdaArn: authInfra.authAcsFunction.qualifiedArn,
            includeBody: true,
          },
        ],
      },
      // SAML metadata endpoint
      {
        pathPattern: config.auth?.saml?.metadataPath || "/saml/metadata",
        targetOriginId: "s3-frontend",
        viewerProtocolPolicy: "https-only",
        allowedMethods: ["GET", "HEAD"],
        cachedMethods: ["GET", "HEAD"],
        compress: true,
        forwardedValues: {
          queryString: false,
          cookies: { forward: "none" },
        },
        minTtl: 0,
        defaultTtl: 0,
        maxTtl: 0,
        lambdaFunctionAssociations: [
          {
            eventType: "viewer-request",
            lambdaArn: authInfra.authMetadataFunction.qualifiedArn,
            includeBody: false,
          },
        ],
      }
    );
  }

  // Create new CloudFront distribution (SST manages everything)
  const distribution = new aws.cloudfront.Distribution(
    "FrontendDistribution",
    {
      enabled: true,
      isIpv6Enabled: true,
      comment: `Dashborion ${stage} - Managed by SST`,
      defaultRootObject: "index.html",
      aliases: [cloudfrontDomain],
      priceClass: "PriceClass_100",

      // Origins
      origins: [
        // S3 origin for static files
        {
          domainName: s3BucketDomainName,
          originId: "s3-frontend",
          originAccessControlId: oac.id,
        },
        // API Gateway origin
        {
          domainName: apiDomain,
          originId: "api-gateway",
          customOriginConfig: {
            httpPort: 80,
            httpsPort: 443,
            originProtocolPolicy: "https-only",
            originSslProtocols: ["TLSv1.2"],
          },
        },
      ],

      // Default behavior (S3 static files)
      defaultCacheBehavior: {
        targetOriginId: "s3-frontend",
        viewerProtocolPolicy: "redirect-to-https",
        allowedMethods: ["GET", "HEAD", "OPTIONS"],
        cachedMethods: ["GET", "HEAD"],
        compress: true,
        forwardedValues: {
          queryString: false,
          cookies: { forward: "none" },
        },
        minTtl: 0,
        defaultTtl: 3600,
        maxTtl: 86400,
        lambdaFunctionAssociations: defaultLambdaAssociations,
      },

      // Ordered behaviors (API, SAML endpoints)
      orderedCacheBehaviors: orderedCacheBehaviors,

      // SPA error handling
      customErrorResponses: [
        {
          errorCode: 404,
          responseCode: 200,
          responsePagePath: "/index.html",
          errorCachingMinTtl: 300,
        },
        {
          errorCode: 403,
          responseCode: 200,
          responsePagePath: "/index.html",
          errorCachingMinTtl: 300,
        },
      ],

      restrictions: {
        geoRestriction: {
          restrictionType: "none",
        },
      },

      viewerCertificate: certificateArn
        ? {
            acmCertificateArn: certificateArn,
            sslSupportMethod: "sni-only",
            minimumProtocolVersion: "TLSv1.2_2021",
          }
        : {
            cloudfrontDefaultCertificate: true,
          },

      tags: {
        Project: "dashborion",
        Stage: stage,
        ManagedBy: "sst",
      },
    }
  );

  // S3 bucket policy for CloudFront OAC access
  // Note: This updates the existing bucket's policy to allow the new CloudFront distribution
  new aws.s3.BucketPolicy("FrontendBucketPolicy", {
    bucket: s3Bucket,
    policy: $interpolate`{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "AllowCloudFrontServicePrincipal",
          "Effect": "Allow",
          "Principal": {
            "Service": "cloudfront.amazonaws.com"
          },
          "Action": "s3:GetObject",
          "Resource": "arn:aws:s3:::${s3Bucket}/*",
          "Condition": {
            "StringEquals": {
              "AWS:SourceArn": "${distribution.arn}"
            }
          }
        }
      ]
    }`,
  });

  // ==========================================================================
  // 6. Return outputs
  // ==========================================================================
  const frontendUrl = `https://${cloudfrontDomain}`;

  const result: Record<string, any> = {
    mode: "managed",
    stage,
    api: api.url,
    frontend: frontendUrl,
    cloudfrontId: distribution.id,
    cloudfrontDomainName: distribution.domainName,
    lambdaRole: config.lambda.roleArn,
    crossAccountRoles: Object.keys(config.crossAccountRoles || {}),
    externalResources: {
      s3Bucket: s3Bucket,
      certificateArn: certificateArn || "default",
    },
    // NOTE: You need to update Route53 to point to the new CloudFront distribution
    // Run: aws route53 change-resource-record-sets with the new CloudFront domain
    route53UpdateRequired: true,
  };

  if (authInfra) {
    result.auth = {
      enabled: true,
      permissionsTable: authInfra.permissionsTable.name,
      auditTable: authInfra.auditTable.name,
      lambdaEdge: {
        protect: authInfra.authProtectFunction.qualifiedArn,
        acs: authInfra.authAcsFunction.qualifiedArn,
        metadata: authInfra.authMetadataFunction.qualifiedArn,
      },
    };
  }

  return result;
}
