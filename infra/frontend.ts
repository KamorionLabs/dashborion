/**
 * Frontend deployment for Dashborion
 * Handles building and deploying frontend to S3 in managed mode
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig } from "./config";

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
