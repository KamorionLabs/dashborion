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

interface InfraConfig {
  mode: "standalone" | "semi-managed" | "managed";
  aws?: {
    region?: string;
    profile?: string;
  };
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

export default $config({
  app(input) {
    // Load config early to get AWS settings
    const config = loadInfraConfig();
    const awsRegion = config.aws?.region || process.env.AWS_REGION || "eu-west-3";
    const awsProfile = config.aws?.profile || process.env.AWS_PROFILE;

    return {
      name: "dashborion",
      removal: input?.stage === "production" ? "retain" : "remove",
      home: "aws",
      providers: {
        aws: {
          region: awsRegion,
          ...(awsProfile ? { profile: awsProfile } : {}),
        },
        "synced-folder": true,
      },
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

  // Build cross-account role ARNs for Lambda environment
  const crossAccountRolesEnv = config.crossAccountRoles
    ? JSON.stringify(config.crossAccountRoles)
    : "{}";

  // Backend: API Gateway + Lambda (SST creates everything)
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
    environment: {
      STAGE: stage,
      PROJECT_NAME: process.env.PROJECT_NAME || "dashborion",
      AWS_REGION_DEFAULT: awsRegion,
      ENVIRONMENTS: process.env.ENVIRONMENTS || "{}",
      SSO_PORTAL_URL: process.env.SSO_PORTAL_URL || "",
      GITHUB_ORG: process.env.GITHUB_ORG || "",
      CROSS_ACCOUNT_ROLES: crossAccountRolesEnv,
    },
    // SST creates IAM role with these permissions
    permissions: [
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
    ],
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
    mode: "standalone",
    stage,
    api: api.url,
    frontend: frontend.url,
    crossAccountRoles: Object.keys(config.crossAccountRoles || {}),
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
