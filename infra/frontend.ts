/**
 * Frontend deployment for Dashborion
 * Handles building and deploying frontend to S3 in managed mode
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig } from "./config";

/**
 * Environment color configuration
 */
const ENV_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  "nh-integration": { bg: "bg-cyan-500", text: "text-cyan-400", border: "border-cyan-500" },
  "nh-staging": { bg: "bg-yellow-500", text: "text-yellow-400", border: "border-yellow-500" },
  "nh-preprod": { bg: "bg-blue-500", text: "text-blue-400", border: "border-blue-500" },
  "nh-production": { bg: "bg-green-500", text: "text-green-400", border: "border-green-500" },
  "legacy-staging": { bg: "bg-orange-500", text: "text-orange-400", border: "border-orange-500" },
  "legacy-preprod": { bg: "bg-indigo-500", text: "text-indigo-400", border: "border-indigo-500" },
  "legacy-production": { bg: "bg-red-500", text: "text-red-400", border: "border-red-500" },
  staging: { bg: "bg-yellow-500", text: "text-yellow-400", border: "border-yellow-500" },
  preprod: { bg: "bg-blue-500", text: "text-blue-400", border: "border-blue-500" },
  production: { bg: "bg-green-500", text: "text-green-400", border: "border-green-500" },
  shared: { bg: "bg-purple-500", text: "text-purple-400", border: "border-purple-500" },
};

/**
 * Generate frontend config.json from infra.config.json
 */
export function generateFrontendConfig(config: InfraConfig, stage: string): Record<string, unknown> {
  const projects: Record<string, unknown> = {};
  // Find first non-comment project key
  const projectKeys = Object.keys(config.projects || {}).filter(k => !k.startsWith("_"));
  const defaultProject = projectKeys[0] || "default";

  // Convert infra.config projects to frontend config format
  for (const [projectId, projectConfig] of Object.entries(config.projects || {})) {
    if (projectId.startsWith("_")) continue; // Skip comments

    // Build environments object preserving full config
    const environments: Record<string, unknown> = {};
    const services = new Set<string>();
    const accounts: Record<string, unknown> = {};
    const envColors: Record<string, unknown> = {};

    for (const [envName, envConfig] of Object.entries(projectConfig.environments || {})) {
      // Skip disabled environments
      if (envConfig.enabled === false) continue;

      // Collect services
      (envConfig.services || []).forEach((s: string) => services.add(s));

      // Build accounts mapping
      accounts[envName] = {
        id: envConfig.accountId,
        alias: `${projectId}-${envName}`,
        region: envConfig.region || config.aws?.region || "eu-central-1",
      };

      // Assign env colors
      envColors[envName] = ENV_COLORS[envName] || ENV_COLORS.staging;

      // Preserve full environment config
      environments[envName] = {
        accountId: envConfig.accountId,
        region: envConfig.region || config.aws?.region || "eu-central-1",
        namespace: envConfig.namespace,
        clusterName: envConfig.clusterName,
        status: envConfig.status,
        infrastructure: envConfig.infrastructure || {},
      };
    }

    // Build pipelines config for frontend
    const pipelinesConfig = projectConfig.pipelines?.enabled
      ? {
          enabled: true,
          providers: (projectConfig.pipelines.providers || []).map(provider => ({
            type: provider.type,
            category: provider.category,
            services: provider.services,
            displayName: provider.displayName || provider.type,
            // Include provider-specific config
            ...(provider.type === "codepipeline" && {
              accountId: (provider as any).accountId,
              region: (provider as any).region || config.aws?.region || "eu-central-1",
            }),
            ...(provider.type === "azure-devops" && {
              organization: (provider as any).organization,
              project: (provider as any).project,
              pipelinePattern: (provider as any).pipelinePattern,
            }),
            ...(provider.type === "github-actions" && {
              owner: (provider as any).owner,
              repoPattern: (provider as any).repoPattern,
              workflowPattern: (provider as any).workflowPattern,
            }),
            ...(provider.type === "bitbucket" && {
              workspace: (provider as any).workspace,
              repoPattern: (provider as any).repoPattern,
            }),
            ...(provider.type === "argocd" && {
              url: (provider as any).url,
              appPattern: (provider as any).appPattern,
            }),
            ...(provider.type === "jenkins" && {
              url: (provider as any).url,
              jobPattern: (provider as any).jobPattern,
            }),
          })),
        }
      : { enabled: false };

    projects[projectId] = {
      name: projectConfig.displayName || projectId,
      shortName: projectId.toUpperCase().substring(0, 4),
      color: "#0ea5e9",
      client: stage,
      description: projectConfig.displayName || projectId,
      aws: { accounts },
      services: Array.from(services),
      environments,
      serviceNaming: { prefix: projectId },
      infrastructure: {
        serviceColors: {},
      },
      envColors,
      pipelines: pipelinesConfig,
      features: projectConfig.features || {},
      topology: projectConfig.topology || null,
    };
  }

  return {
    global: {
      title: `${stage.charAt(0).toUpperCase() + stage.slice(1)} Operations`,
      logo: "/kamorion-logo.png",
      logoAlt: stage,
      ssoPortalUrl: config.ssoPortalUrl || "",
      defaultRegion: config.aws?.region || "eu-central-1",
    },
    api: {
      baseUrl: "/api",
      refreshIntervals: {
        dashboard: 30000,
        logs: 3000,
      },
    },
    auth: {
      logoutUrl: "/saml/logout",
      deviceAuthPath: "/auth/device",
    },
    features: config.features || { pipelines: false },
    projects,
    defaultProject,
  };
}

/**
 * Frontend deployment output
 */
export interface FrontendOutput {
  url: string;
  cloudfrontId: string;
  s3Bucket: string;
}

/**
 * Build frontend with optional API URL injection
 */
export async function buildFrontend(apiDomain: string | null): Promise<void> {
  const fs = await import("fs");
  const path = await import("path");
  const { execSync } = await import("child_process");

  const frontendPath = path.join(process.cwd(), "packages/frontend");

  if (!fs.existsSync(frontendPath)) {
    console.log("Warning: Frontend package not found at packages/frontend");
    return;
  }

  console.log("Building frontend...");
  try {
    const buildEnv: Record<string, string> = {
      ...process.env as Record<string, string>,
      NODE_ENV: "production",
    };

    // Inject direct API URL if custom domain is configured
    if (apiDomain) {
      buildEnv.VITE_API_URL = `https://${apiDomain}`;
      console.log(`Frontend will use direct API: https://${apiDomain}`);
    }

    execSync("npm run build", {
      cwd: frontendPath,
      stdio: "inherit",
      env: buildEnv,
    });
    console.log("Frontend build complete.");
  } catch (err) {
    console.error("Frontend build failed:", err);
    throw err;
  }
}

/**
 * Deploy frontend to S3 bucket (managed mode)
 */
export async function deployFrontendToS3(
  config: InfraConfig,
  stage: string
): Promise<FrontendOutput> {
  const fs = await import("fs");
  const path = await import("path");

  const frontendDistPath = path.join(process.cwd(), "packages/frontend/dist");
  const s3Bucket = config.frontend?.s3Bucket || "";
  const cloudfrontId = config.frontend?.cloudfrontDistributionId || "";
  const url = config.frontend?.cloudfrontDomain
    ? `https://${config.frontend.cloudfrontDomain}`
    : "";

  if (!fs.existsSync(frontendDistPath)) {
    console.log("Warning: Frontend dist not found. Run 'npm run build' in packages/frontend first.");
    return { url, cloudfrontId, s3Bucket };
  }

  // Generate config.json from infra.config.json and write to dist
  const frontendConfig = generateFrontendConfig(config, stage);
  const configPath = path.join(frontendDistPath, "config.json");
  fs.writeFileSync(configPath, JSON.stringify(frontendConfig, null, 2));
  console.log(`Generated config.json for stage '${stage}' with ${Object.keys(frontendConfig.projects as object).length} projects`);

  if (!s3Bucket) {
    console.log("Warning: No S3 bucket configured for frontend deployment.");
    return { url, cloudfrontId, s3Bucket };
  }

  // Import AWS SDK
  const { S3Client, PutObjectCommand, ListObjectsV2Command, DeleteObjectsCommand } = await import("@aws-sdk/client-s3");
  const { fromNodeProviderChain } = await import("@aws-sdk/credential-providers");
  const mime = await import("mime-types");

  const s3Client = new S3Client({
    region: config.aws?.region || "eu-west-3",
    credentials: fromNodeProviderChain({ profile: config.aws?.profile }),
  });

  // Get all files from dist recursively
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

  return { url, cloudfrontId, s3Bucket };
}
