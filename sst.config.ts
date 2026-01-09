/// <reference path="./.sst/platform/config.d.ts" />

/**
 * SST Configuration for Dashborion
 *
 * This configuration uses SST v3 native components.
 *
 * Configuration:
 *   - Set DASHBORION_CONFIG_DIR env var to external config directory
 *   - Or create infra.config.json from infra.config.example.json
 *
 * Deployment:
 *   - npx sst dev (development with live reload)
 *   - npx sst deploy --stage homebox (production)
 *
 * SSO Lambda@Edge:
 *   - Deployed to us-east-1 (required for CloudFront)
 *   - ARNs stored in SSM for Terraform to reference
 *   - Config baked at build time (Lambda@Edge doesn't support env vars)
 */

// Configuration types from external config file
interface InfraConfigFile {
  mode: "standalone" | "semi-managed" | "managed";
  aws?: {
    region?: string;
    profile?: string;
  };
  auth?: {
    enabled?: boolean;
    provider?: "saml" | "oidc" | "simple" | "none";
    saml?: {
      entityId: string;
      idpMetadataFile?: string;
      idpMetadataUrl?: string;
      acsPath?: string;
      metadataPath?: string;
    };
    users?: Record<string, {
      password: string;
      role: "admin" | "operator" | "viewer";
      groups?: string[];
      projects?: string[];
    }>;
    sessionTtlSeconds?: number;
    cookieDomain?: string;
    sessionEncryptionKey?: string;
    excludedPaths?: string[];
    requireMfaForProduction?: boolean;
  };
  lambda?: {
    roleArn?: string;
  };
  frontend?: {
    s3Bucket?: string;
    s3BucketArn?: string;
    s3BucketDomainName?: string;
    cloudfrontDistributionId?: string;
    cloudfrontDomain?: string;
    certificateArn?: string;
    originAccessControlId?: string;
  };
  apiGateway?: {
    id?: string;
    url?: string;
  };
  crossAccountRoles?: Record<
    string,
    {
      readRoleArn: string;
      actionRoleArn?: string;
    }
  >;
  projects?: Record<
    string,
    {
      displayName: string;
      environments: Record<
        string,
        {
          accountId: string;
          region?: string;
          services: string[];
          clusterName?: string;
          namespace?: string;
        }
      >;
      idpGroupMapping?: Record<string, any>;
    }
  >;
}

// Get config directory (supports external config via DASHBORION_CONFIG_DIR)
function getConfigDir(): string {
  return process.env.DASHBORION_CONFIG_DIR || process.cwd();
}

// Load infrastructure config (sync, for app() function)
function loadInfraConfigSync(): InfraConfigFile {
  const fs = require("fs");
  const path = require("path");

  const configDir = getConfigDir();
  const externalConfig = path.join(configDir, "infra.config.json");
  const localConfig = path.join(process.cwd(), "infra.config.json");
  const exampleConfig = path.join(process.cwd(), "infra.config.example.json");

  // Priority 1: External config directory
  if (process.env.DASHBORION_CONFIG_DIR && fs.existsSync(externalConfig)) {
    console.log(`Loading config from: ${externalConfig}`);
    return JSON.parse(fs.readFileSync(externalConfig, "utf-8"));
  }

  // Priority 2: Local config (gitignored)
  if (fs.existsSync(localConfig)) {
    console.log(`Loading config from: ${localConfig}`);
    return JSON.parse(fs.readFileSync(localConfig, "utf-8"));
  }

  // Priority 3: Example config (for development)
  if (fs.existsSync(exampleConfig)) {
    console.log(
      `Loading example config from: ${exampleConfig}`
    );
    return JSON.parse(fs.readFileSync(exampleConfig, "utf-8"));
  }

  // Default: standalone mode
  console.log("No config found, using standalone mode");
  return { mode: "standalone" };
}

export default $config({
  app(input) {
    const config = loadInfraConfigSync();
    return {
      name: "dashborion",
      removal: input?.stage === "production" ? "retain" : "remove",
      protect: ["production"].includes(input?.stage),
      home: "aws",
      providers: {
        aws: {
          region: config.aws?.region || "eu-west-3",
          ...(config.aws?.profile ? { profile: config.aws.profile } : {}),
        },
      },
    };
  },
  async run() {
    const fs = await import("fs");
    const path = await import("path");

    const stage = $app.stage;
    const configDir = getConfigDir();
    const config = loadInfraConfigSync();

    console.log(`Deploying Dashborion (stage: ${stage}, mode: ${config.mode})`);

    // Convert cross-account roles (skip _comment keys)
    const crossAccountRoles: Record<string, { readRoleArn: string; actionRoleArn?: string }> = {};
    if (config.crossAccountRoles) {
      for (const [accountId, role] of Object.entries(config.crossAccountRoles)) {
        if (accountId.startsWith("_") || typeof role !== "object" || role === null) {
          continue;
        }
        crossAccountRoles[accountId] = {
          readRoleArn: role.readRoleArn,
          actionRoleArn: role.actionRoleArn,
        };
      }
    }

    // Convert projects (skip _comment keys)
    const projects: Record<string, { displayName: string; environments: Record<string, any> }> = {};
    if (config.projects) {
      for (const [id, project] of Object.entries(config.projects)) {
        if (id.startsWith("_") || typeof project !== "object" || project === null) {
          continue;
        }
        const environments: Record<string, any> = {};
        if (project.environments) {
          for (const [envId, env] of Object.entries(project.environments)) {
            if (envId.startsWith("_") || typeof env !== "object" || env === null) {
              continue;
            }
            environments[envId] = {
              accountId: env.accountId,
              region: env.region || config.aws?.region || "eu-west-3",
              clusterName: env.clusterName,
              namespace: env.namespace,
            };
          }
        }
        projects[id] = {
          displayName: project.displayName,
          environments,
        };
      }
    }

    // Projects need to include services list from original config
    const projectsWithServices: Record<string, any> = {};
    if (config.projects) {
      for (const [id, project] of Object.entries(config.projects)) {
        if (id.startsWith("_") || typeof project !== "object" || project === null) {
          continue;
        }
        const environments: Record<string, any> = {};
        if (project.environments) {
          for (const [envId, env] of Object.entries(project.environments)) {
            if (envId.startsWith("_") || typeof env !== "object" || env === null) {
              continue;
            }
            environments[envId] = {
              accountId: env.accountId,
              region: env.region || config.aws?.region || "eu-west-3",
              clusterName: env.clusterName,
              namespace: env.namespace,
              services: env.services || [],
            };
          }
        }
        projectsWithServices[id] = {
          displayName: project.displayName,
          environments,
          idpGroupMapping: project.idpGroupMapping,
        };
      }
    }

    // Determine domain
    const domain = config.frontend?.cloudfrontDomain || `dashboard-${stage}.example.com`;

    // Create Backend API using SST's native Function component
    const api = new sst.aws.ApiGatewayV2("DashborionApi", {
      cors: {
        allowOrigins: [`https://${domain}`],
        allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allowHeaders: ["Content-Type", "Authorization", "x-sso-user-email"],
      },
    });

    // Create DynamoDB table for auth tokens
    const tokensTable = new sst.aws.Dynamo("TokensTable", {
      fields: {
        pk: "string",
        sk: "string",
      },
      primaryIndex: { hashKey: "pk", rangeKey: "sk" },
      ttl: "ttl",
    });

    // Create DynamoDB table for device codes (CLI auth flow)
    // Uses pk/sk pattern like TokensTable for consistency with backend code
    const deviceCodesTable = new sst.aws.Dynamo("DeviceCodesTable", {
      fields: {
        pk: "string",
        sk: "string",
      },
      primaryIndex: { hashKey: "pk", rangeKey: "sk" },
      ttl: "ttl",
    });

    // Create the Lambda function for the API
    // Use root handler.py wrapper that sets up Python path correctly
    // copyFiles ensures handler.py is at bundle root where Lambda expects it
    const apiHandler = new sst.aws.Function("ApiHandler", {
      handler: "handler.lambda_handler",
      runtime: "python3.12",
      architecture: "arm64",
      memory: "256 MB",
      timeout: "30 seconds",
      copyFiles: [
        { from: "handler.py", to: "handler.py" },
        { from: "backend", to: "backend" },
      ],
      link: [tokensTable, deviceCodesTable],
      environment: {
        // Backend expects individual env vars, not a single DASHBORION_CONFIG
        AWS_REGION_DEFAULT: config.aws?.region || "eu-west-3",
        PROJECTS: JSON.stringify(projectsWithServices),
        CROSS_ACCOUNT_ROLES: JSON.stringify(crossAccountRoles),
        CORS_ORIGINS: `https://${domain}`,
        // Auth configuration
        AUTH_PROVIDER: config.auth?.provider || "simple",
        AUTH_USERS: JSON.stringify(config.auth?.users || {}),
        TOKENS_TABLE_NAME: tokensTable.name,
        DEVICE_CODES_TABLE_NAME: deviceCodesTable.name,
      },
      permissions: [
        // Allow assuming cross-account roles
        {
          actions: ["sts:AssumeRole"],
          resources: Object.values(crossAccountRoles).flatMap(r =>
            [r.readRoleArn, r.actionRoleArn].filter(Boolean) as string[]
          ),
        },
        // CodePipeline permissions (shared-services account)
        {
          actions: [
            "codepipeline:GetPipelineState",
            "codepipeline:ListPipelineExecutions",
            "codepipeline:GetPipelineExecution",
            "codepipeline:StartPipelineExecution",
          ],
          resources: ["arn:aws:codepipeline:eu-west-3:501994300510:homebox-*"],
        },
        // CodeBuild permissions (for build logs)
        {
          actions: [
            "codebuild:BatchGetBuilds",
            "codebuild:ListBuildsForProject",
          ],
          resources: ["arn:aws:codebuild:eu-west-3:501994300510:project/homebox-*"],
        },
        // ECR permissions (shared-services account)
        {
          actions: [
            "ecr:DescribeImages",
            "ecr:DescribeRepositories",
            "ecr:ListImages",
          ],
          resources: ["arn:aws:ecr:eu-west-3:501994300510:repository/homebox-*"],
        },
        // CloudWatch Logs permissions (for build/deploy logs)
        {
          actions: [
            "logs:GetLogEvents",
            "logs:FilterLogEvents",
            "logs:DescribeLogStreams",
          ],
          resources: ["arn:aws:logs:eu-west-3:501994300510:log-group:/aws/codebuild/homebox-*:*"],
        },
      ],
    });

    // Add routes to API Gateway
    api.route("GET /api/{proxy+}", apiHandler.arn);
    api.route("POST /api/{proxy+}", apiHandler.arn);
    api.route("PUT /api/{proxy+}", apiHandler.arn);
    api.route("DELETE /api/{proxy+}", apiHandler.arn);

    // Add health check route
    api.route("GET /api/health", apiHandler.arn);

    // ==========================================================================
    // SSO Lambda@Edge (only in managed mode with SAML auth)
    // ==========================================================================
    let ssoLambdaArns: {
      protect?: string;
      acs?: string;
      metadata?: string;
    } = {};

    const enableSso = config.mode === "managed" && config.auth?.provider === "saml";

    if (enableSso) {
      const { execSync } = await import("child_process");
      const authPackagePath = path.join(process.cwd(), "packages/auth");
      const authDistPath = path.join(authPackagePath, "dist");

      // Build auth package (injects config at build time)
      console.log("Building SSO Lambda@Edge handlers...");
      try {
        execSync("npm run build", {
          cwd: authPackagePath,
          stdio: "inherit",
          env: {
            ...process.env,
            DASHBORION_CONFIG_DIR: configDir,
          },
        });
        console.log("SSO Lambda@Edge build complete.");
      } catch (err) {
        console.error("SSO Lambda@Edge build failed:", err);
        throw err;
      }

      // Create us-east-1 provider for Lambda@Edge
      const usEast1Provider = new aws.Provider("UsEast1Provider", {
        region: "us-east-1",
        profile: config.aws?.profile,
      });

      // Create Lambda@Edge execution role
      const edgeRole = new aws.iam.Role("SsoEdgeRole", {
        assumeRolePolicy: JSON.stringify({
          Version: "2012-10-17",
          Statement: [
            {
              Action: "sts:AssumeRole",
              Effect: "Allow",
              Principal: {
                Service: ["lambda.amazonaws.com", "edgelambda.amazonaws.com"],
              },
            },
          ],
        }),
        tags: {
          Project: "dashborion",
          Stage: stage,
        },
      }, { provider: usEast1Provider });

      new aws.iam.RolePolicyAttachment("SsoEdgeBasicPolicy", {
        role: edgeRole.name,
        policyArn: "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
      }, { provider: usEast1Provider });

      // Deploy Lambda@Edge functions to us-east-1
      const handlers = ["protect", "acs", "metadata"] as const;
      const lambdaFunctions: Record<string, aws.lambda.Function> = {};

      for (const handler of handlers) {
        const handlerPath = path.join(authDistPath, handler);

        if (!fs.existsSync(handlerPath)) {
          console.warn(`Warning: SSO handler not found: ${handlerPath}`);
          continue;
        }

        // Create Lambda function with publish=true for Lambda@Edge
        const fn = new aws.lambda.Function(`SsoEdge${handler.charAt(0).toUpperCase() + handler.slice(1)}`, {
          name: `dashborion-${stage}-sso-${handler}`,
          runtime: "nodejs20.x",
          handler: "index.handler",
          code: new $util.asset.FileArchive(handlerPath),
          role: edgeRole.arn,
          memorySize: 128,
          timeout: handler === "acs" ? 10 : 5, // ACS needs more time for SAML parsing
          publish: true, // Required for Lambda@Edge
          tags: {
            Project: "dashborion",
            Stage: stage,
            Component: "sso",
          },
        }, { provider: usEast1Provider });

        lambdaFunctions[handler] = fn;
      }

      // Store qualified ARNs for CloudFront association
      if (lambdaFunctions.protect) {
        ssoLambdaArns.protect = lambdaFunctions.protect.qualifiedArn;
      }
      if (lambdaFunctions.acs) {
        ssoLambdaArns.acs = lambdaFunctions.acs.qualifiedArn;
      }
      if (lambdaFunctions.metadata) {
        ssoLambdaArns.metadata = lambdaFunctions.metadata.qualifiedArn;
      }

      // Store ARNs in SSM Parameter Store for Terraform to reference
      const ssmPrefix = `/dashborion/${stage}/sso`;

      if (ssoLambdaArns.protect) {
        new aws.ssm.Parameter("SsoProtectArn", {
          name: `${ssmPrefix}/lambda-protect-arn`,
          type: "String",
          value: ssoLambdaArns.protect,
          tags: { Project: "dashborion", Stage: stage },
        });
      }

      if (ssoLambdaArns.acs) {
        new aws.ssm.Parameter("SsoAcsArn", {
          name: `${ssmPrefix}/lambda-acs-arn`,
          type: "String",
          value: ssoLambdaArns.acs,
          tags: { Project: "dashborion", Stage: stage },
        });
      }

      if (ssoLambdaArns.metadata) {
        new aws.ssm.Parameter("SsoMetadataArn", {
          name: `${ssmPrefix}/lambda-metadata-arn`,
          type: "String",
          value: ssoLambdaArns.metadata,
          tags: { Project: "dashborion", Stage: stage },
        });
      }

      console.log(`SSO Lambda@Edge ARNs stored in SSM: ${ssmPrefix}/lambda-*-arn`);
    }

    // Determine outputs based on mode
    let url: string;
    let cloudfrontId: string;
    let s3Bucket: string;

    if (config.mode === "managed" && config.frontend) {
      // Use existing external infrastructure (created by Terraform)
      url = `https://${config.frontend.cloudfrontDomain}`;
      cloudfrontId = config.frontend.cloudfrontDistributionId || "";
      s3Bucket = config.frontend.s3Bucket || "";

      // Build and deploy frontend to existing S3 bucket
      const frontendPath = path.join(process.cwd(), "packages/frontend");
      const frontendDistPath = path.join(frontendPath, "dist");

      // Build frontend if source exists
      if (fs.existsSync(frontendPath) && s3Bucket) {
        const { execSync } = await import("child_process");

        console.log("Building frontend...");
        try {
          execSync("npm run build", {
            cwd: frontendPath,
            stdio: "inherit",
            env: { ...process.env, NODE_ENV: "production" },
          });
          console.log("Frontend build complete.");
        } catch (err) {
          console.error("Frontend build failed:", err);
          throw err;
        }
      }

      if (fs.existsSync(frontendDistPath) && s3Bucket) {
        // Deploy frontend using AWS SDK (more reliable than synced-folder with SST)
        const { S3Client, PutObjectCommand, ListObjectsV2Command, DeleteObjectsCommand } = await import("@aws-sdk/client-s3");
        const { fromNodeProviderChain } = await import("@aws-sdk/credential-providers");
        const mime = await import("mime-types");

        const s3Client = new S3Client({
          region: config.aws?.region || "eu-west-3",
          credentials: fromNodeProviderChain({ profile: config.aws?.profile }),
        });

        // Get all files from dist
        const getAllFiles = (dir: string, base = ""): string[] => {
          const entries = fs.readdirSync(dir, { withFileTypes: true });
          const files: string[] = [];
          for (const entry of entries) {
            const fullPath = path.join(dir, entry.name);
            const relativePath = base ? `${base}/${entry.name}` : entry.name;
            if (entry.isDirectory()) {
              files.push(...getAllFiles(fullPath, relativePath));
            } else {
              files.push(relativePath);
            }
          }
          return files;
        };

        const files = getAllFiles(frontendDistPath);
        console.log(`Uploading ${files.length} files to s3://${s3Bucket}/...`);

        // Upload all files
        for (const file of files) {
          const filePath = path.join(frontendDistPath, file);
          const content = fs.readFileSync(filePath);
          const contentType = mime.lookup(file) || "application/octet-stream";

          await s3Client.send(new PutObjectCommand({
            Bucket: s3Bucket,
            Key: file,
            Body: content,
            ContentType: contentType as string,
          }));
        }
        console.log(`Frontend uploaded to s3://${s3Bucket}/`);

        // Clean up old files not in current build
        const listResult = await s3Client.send(new ListObjectsV2Command({ Bucket: s3Bucket }));
        const existingKeys = listResult.Contents?.map(obj => obj.Key!) || [];
        const toDelete = existingKeys.filter(key => !files.includes(key));

        if (toDelete.length > 0) {
          await s3Client.send(new DeleteObjectsCommand({
            Bucket: s3Bucket,
            Delete: { Objects: toDelete.map(Key => ({ Key })) },
          }));
          console.log(`Cleaned up ${toDelete.length} old files`);
        }

        // CloudFront invalidation
        if (cloudfrontId) {
          const { CloudFrontClient, CreateInvalidationCommand } = await import("@aws-sdk/client-cloudfront");

          const cfClient = new CloudFrontClient({
            region: "us-east-1",
            credentials: fromNodeProviderChain({ profile: config.aws?.profile }),
          });

          const callerRef = `sst-${stage}-${Date.now()}`;
          try {
            const result = await cfClient.send(new CreateInvalidationCommand({
              DistributionId: cloudfrontId,
              InvalidationBatch: {
                Paths: { Quantity: 1, Items: ["/*"] },
                CallerReference: callerRef,
              },
            }));
            console.log(`CloudFront invalidation created: ${result.Invalidation?.Id}`);
          } catch (err) {
            console.error(`CloudFront invalidation failed:`, err);
          }
        }
      } else {
        console.log("Warning: Frontend dist not found. Run 'npm run build' in packages/frontend first.");
      }
    } else {
      // Standalone mode - just use API URL directly
      url = api.url;
      cloudfrontId = "";
      s3Bucket = "";
    }

    return {
      url,
      cloudfrontId,
      apiUrl: api.url,
      s3Bucket,
      // SSO Lambda@Edge ARNs (for Terraform reference via SSM)
      ssoEnabled: enableSso,
      ...(enableSso && ssoLambdaArns.protect && { ssoLambdaProtectArn: ssoLambdaArns.protect }),
      ...(enableSso && ssoLambdaArns.acs && { ssoLambdaAcsArn: ssoLambdaArns.acs }),
      ...(enableSso && ssoLambdaArns.metadata && { ssoLambdaMetadataArn: ssoLambdaArns.metadata }),
    };
  },
});
