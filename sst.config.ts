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
    cloudfrontDistributionId?: string;
    cloudfrontDomain?: string;
  };
  apiGateway?: {
    id?: string;
    url?: string;
  };
  crossAccountRoles?: Record<string, CrossAccountRole>;
}

// Load infrastructure config (sync version for app() function)
function loadInfraConfig(): InfraConfig {
  // Use require for sync loading in app() context
  const fs = require("fs");
  const path = require("path");
  const configPath = path.join(process.cwd(), "infra.config.json");

  if (fs.existsSync(configPath)) {
    const content = fs.readFileSync(configPath, "utf-8");
    return JSON.parse(content);
  }

  // Default: standalone mode
  return { mode: "standalone" };
}

// Auth infrastructure outputs
interface AuthInfraOutput {
  permissionsTable: any;
  auditTable: any;
  authProtectFunction: any;
  authAcsFunction: any;
  authMetadataFunction: any;
  encryptionKey: any;
}

/**
 * Create authentication infrastructure
 * - KMS key for session encryption
 * - DynamoDB tables for permissions and audit
 * - Lambda@Edge functions for CloudFront auth
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
  const authProtectFunction = new aws.lambda.Function(
    "AuthProtect",
    {
      functionName: `dashborion-${stage}-auth-protect`,
      handler: "index.handler",
      runtime: "nodejs20.x",
      timeout: 5, // Lambda@Edge viewer-request max is 5 seconds
      memorySize: 128,
      role: edgeRole.arn,
      // For Lambda@Edge, we need to bundle the code
      // SST will handle this through the build process
      code: new $util.asset.FileArchive("auth/dist/protect"),
      publish: true, // Lambda@Edge requires published versions
      tags: {
        Project: "dashborion",
        Stage: stage,
        Purpose: "auth-protect",
      },
    },
    { provider: $providers["aws-us-east-1"] }
  );

  // Lambda@Edge: ACS (origin-request for /saml/acs)
  const authAcsFunction = new aws.lambda.Function(
    "AuthAcs",
    {
      functionName: `dashborion-${stage}-auth-acs`,
      handler: "index.handler",
      runtime: "nodejs20.x",
      timeout: 10, // Origin-request allows up to 30 seconds
      memorySize: 256, // SAML parsing needs more memory
      role: edgeRole.arn,
      code: new $util.asset.FileArchive("auth/dist/acs"),
      publish: true,
      tags: {
        Project: "dashborion",
        Stage: stage,
        Purpose: "auth-acs",
      },
    },
    { provider: $providers["aws-us-east-1"] }
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
      code: new $util.asset.FileArchive("auth/dist/metadata"),
      publish: true,
      tags: {
        Project: "dashborion",
        Stage: stage,
        Purpose: "auth-metadata",
      },
    },
    { provider: $providers["aws-us-east-1"] }
  );

  return {
    permissionsTable,
    auditTable,
    authProtectFunction,
    authAcsFunction,
    authMetadataFunction,
    encryptionKey,
  };
}

export default $config({
  app(input) {
    // Load config early to get AWS settings
    const config = loadInfraConfig();
    const awsRegion = config.aws?.region || process.env.AWS_REGION || "eu-west-3";
    const awsProfile = config.aws?.profile || process.env.AWS_PROFILE;
    const authEnabled = config.auth?.enabled ?? false;

    const providers: Record<string, any> = {
      aws: {
        region: awsRegion,
        ...(awsProfile ? { profile: awsProfile } : {}),
      },
      "synced-folder": true,
    };

    // Add us-east-1 provider for Lambda@Edge if auth is enabled
    if (authEnabled) {
      providers["aws-us-east-1"] = {
        region: "us-east-1",
        ...(awsProfile ? { profile: awsProfile } : {}),
      };
    }

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
    backendEnv.PERMISSIONS_TABLE_NAME = authInfra.permissionsTable.name;
    backendEnv.AUDIT_TABLE_NAME = authInfra.auditTable.name;
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

  // Add DynamoDB permissions if auth is enabled
  if (authInfra) {
    backendPermissions.push(
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem"
    );
  }

  // Backend: API Gateway + Lambda (SST creates everything)
  const api = new sst.aws.ApiGatewayV2("DashborionApi", {
    cors: {
      allowOrigins: isProd
        ? [customDomain ? `https://${customDomain}` : "*"]
        : ["*"],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key", "X-Auth-User-Id", "X-Auth-User-Email"],
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

  api.route("GET /api/{proxy+}", apiHandler.arn);
  api.route("POST /api/{proxy+}", apiHandler.arn);
  api.route("PUT /api/{proxy+}", apiHandler.arn);
  api.route("DELETE /api/{proxy+}", apiHandler.arn);
  api.route("GET /health", apiHandler.arn);

  // Auth endpoint for frontend to get user info
  if (authInfra) {
    api.route("GET /api/auth/me", apiHandler.arn);
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
  const path = require("path");
  const frontendPath = path.join(process.cwd(), "frontend");
  const distPath = path.join(frontendPath, "dist");

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
  const syncedFolder = new synced.S3BucketFolder("FrontendSync", {
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
 * - Frontend: SST creates S3 + CloudFront
 * - Backend: Lambda uses external IAM role
 */
async function runSemiManagedMode(stage: string, isProd: boolean, awsRegion: string, config: InfraConfig) {
  // Validate required config
  if (!config.lambda?.roleArn) {
    throw new Error("lambda.roleArn is required in semi-managed mode");
  }

  const customDomain = process.env.DASHBOARD_DOMAIN;

  // Build cross-account role ARNs for Lambda environment
  const crossAccountRolesEnv = config.crossAccountRoles
    ? JSON.stringify(config.crossAccountRoles)
    : "{}";

  // Backend: API Gateway + Lambda with external role
  const api = new sst.aws.ApiGatewayV2("DashborionApi", {
    cors: {
      allowOrigins: isProd
        ? [customDomain ? `https://${customDomain}` : "*"]
        : ["*"],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key"],
    },
  });

  const apiHandler = new sst.aws.Function("ApiHandler", {
    handler: "backend/handler.lambda_handler",
    runtime: "python3.11",
    timeout: "30 seconds",
    memory: "512 MB",
    role: config.lambda.roleArn,
    environment: {
      STAGE: stage,
      PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
      AWS_REGION_DEFAULT: awsRegion,
      ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
      SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
      GITHUB_ORG: process.env.GITHUB_ORG || "",
      CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
    },
  });

  api.route("GET /api/{proxy+}", apiHandler.arn);
  api.route("POST /api/{proxy+}", apiHandler.arn);
  api.route("PUT /api/{proxy+}", apiHandler.arn);
  api.route("DELETE /api/{proxy+}", apiHandler.arn);
  api.route("GET /health", apiHandler.arn);

  // Frontend: Static Site (SST creates S3 + CloudFront)
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

  return {
    mode: "semi-managed",
    stage,
    api: api.url,
    frontend: frontend.url,
    lambdaRole: config.lambda.roleArn,
    crossAccountRoles: Object.keys(config.crossAccountRoles || {}),
  };
}

/**
 * MANAGED MODE
 * SST syncs to existing resources
 * - Frontend: Syncs to existing S3 bucket + invalidates CloudFront
 * - Backend: Lambda uses existing IAM role
 * - API Gateway: SST-managed or existing
 */
async function runManagedMode(stage: string, awsRegion: string, config: InfraConfig) {
  // Validate required config
  if (!config.lambda?.roleArn) {
    throw new Error("lambda.roleArn is required in managed mode");
  }
  if (!config.frontend?.s3Bucket) {
    throw new Error("frontend.s3Bucket is required in managed mode");
  }

  // Build cross-account role ARNs for Lambda environment
  const crossAccountRolesEnv = config.crossAccountRoles
    ? JSON.stringify(config.crossAccountRoles)
    : "{}";

  let apiUrl: string;

  if (config.apiGateway?.id && config.apiGateway?.url) {
    // Use existing API Gateway - SST only deploys Lambda
    const apiHandler = new sst.aws.Function("ApiHandler", {
      handler: "backend/handler.lambda_handler",
      runtime: "python3.11",
      timeout: "30 seconds",
      memory: "512 MB",
      role: config.lambda.roleArn,
      environment: {
        STAGE: stage,
        PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
        AWS_REGION_DEFAULT: awsRegion,
        ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
        SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
        GITHUB_ORG: process.env.GITHUB_ORG || "",
        CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
      },
    });

    apiUrl = config.apiGateway.url;

    // Output Lambda ARN for external integration
    new sst.Linkable("LambdaConfig", {
      properties: {
        arn: apiHandler.arn,
        name: apiHandler.name,
      },
    });

  } else {
    // SST creates API Gateway, but Lambda uses existing role
    const api = new sst.aws.ApiGatewayV2("DashborionApi", {
      cors: {
        allowOrigins: ["*"],
        allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allowHeaders: ["Content-Type", "Authorization", "X-Amz-Date", "X-Api-Key"],
      },
    });

    const apiHandler = new sst.aws.Function("ApiHandler", {
      handler: "backend/handler.lambda_handler",
      runtime: "python3.11",
      timeout: "30 seconds",
      memory: "512 MB",
      role: config.lambda.roleArn,
      environment: {
        STAGE: stage,
        PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
        AWS_REGION_DEFAULT: awsRegion,
        ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
        SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
        GITHUB_ORG: process.env.GITHUB_ORG || "",
        CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
      },
    });

    api.route("GET /api/{proxy+}", apiHandler.arn);
    api.route("POST /api/{proxy+}", apiHandler.arn);
    api.route("PUT /api/{proxy+}", apiHandler.arn);
    api.route("DELETE /api/{proxy+}", apiHandler.arn);
    api.route("GET /health", apiHandler.arn);

    apiUrl = api.url;
  }

  // Frontend: Build and sync to existing S3 bucket
  const path = require("path");
  const frontendPath = path.join(process.cwd(), "frontend");
  const distPath = path.join(frontendPath, "dist");

  // Build frontend with environment variables
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

  // Sync to S3 using synced-folder provider (uses AWS provider credentials)
  const s3Bucket = config.frontend.s3Bucket;
  const cloudfrontId = config.frontend.cloudfrontDistributionId;

  // Use synced-folder to upload frontend assets to existing S3 bucket
  const syncedFolder = new synced.S3BucketFolder("FrontendSync", {
    path: distPath,
    bucketName: s3Bucket,
    acl: "private",
    managedObjects: true, // Delete files not in source
  });

  // CloudFront invalidation (if configured)
  if (cloudfrontId) {
    // Create invalidation using AWS provider
    new aws.cloudfront.Invalidation("CloudFrontInvalidation", {
      distributionId: cloudfrontId,
      invalidationBatch: {
        paths: {
          items: ["/*"],
          quantity: 1,
        },
        callerReference: `sst-deploy-${Date.now()}`,
      },
    }, { dependsOn: [syncedFolder] });
  }

  // Determine frontend URL
  const frontendUrl = config.frontend.cloudfrontDomain
    ? `https://${config.frontend.cloudfrontDomain}`
    : `s3://${s3Bucket}`;

  return {
    mode: "managed",
    stage,
    api: apiUrl,
    frontend: frontendUrl,
    lambdaRole: config.lambda.roleArn,
    crossAccountRoles: Object.keys(config.crossAccountRoles || {}),
    externalResources: {
      s3Bucket: config.frontend.s3Bucket,
      cloudfrontId: config.frontend.cloudfrontDistributionId || null,
      apiGatewayId: config.apiGateway?.id || "SST-managed",
    },
  };
}
