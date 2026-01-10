/// <reference path="./.sst/platform/config.d.ts" />

/**
 * SST Configuration for Dashborion
 *
 * This configuration uses modular infrastructure components from the infra/ directory.
 *
 * Configuration:
 *   - Set DASHBORION_CONFIG_DIR env var to external config directory
 *   - Or create infra.config.json from infra.config.example.json
 *
 * Deployment:
 *   - npx sst dev (development with live reload)
 *   - npx sst deploy --stage <stage> (production)
 *
 * Modes:
 *   - standalone: SST creates all resources (DynamoDB, IAM roles, etc.)
 *   - managed: References existing resources created by Terraform/OpenTofu
 */

// Config loading must be sync and at module level for app() function
function loadConfigSync() {
  const fs = require("fs");
  const path = require("path");
  const configDir = process.env.DASHBORION_CONFIG_DIR || process.cwd();
  const externalConfig = path.join(configDir, "infra.config.json");
  const localConfig = path.join(process.cwd(), "infra.config.json");
  const exampleConfig = path.join(process.cwd(), "infra.config.example.json");

  if (process.env.DASHBORION_CONFIG_DIR && fs.existsSync(externalConfig)) {
    return JSON.parse(fs.readFileSync(externalConfig, "utf-8"));
  }
  if (fs.existsSync(localConfig)) {
    return JSON.parse(fs.readFileSync(localConfig, "utf-8"));
  }
  if (fs.existsSync(exampleConfig)) {
    return JSON.parse(fs.readFileSync(exampleConfig, "utf-8"));
  }
  return { mode: "standalone" };
}

export default $config({
  app(input) {
    const config = loadConfigSync();
    return {
      name: config.naming?.app || "dashborion",
      removal: input?.stage === "production" ? "retain" : "remove",
      protect: ["production"].includes(input?.stage),
      home: "aws",
      providers: {
        aws: {
          region: (config.aws?.region || "eu-west-3") as aws.Region,
          ...(config.aws?.profile ? { profile: config.aws.profile } : {}),
        },
      },
    };
  },

  async run() {
    // Dynamic imports for SST compatibility
    const infra = await import("./infra");
    const {
      loadConfig,
      getConfigDir,
      createNaming,
      createTags,
      createDynamoDBTables,
      createKmsKey,
      createLambdaFunctions,
      getApiDomain,
      createApiCertificate,
      createApiGateway,
      createApiDnsRecord,
      setupAuthorizer,
      setupRoutes,
      buildFrontend,
      deployFrontendToS3,
    } = infra;

    const stage = $app.stage;
    const configDir = getConfigDir();
    const config = loadConfig();

    console.log(`Deploying Dashborion (stage: ${stage}, mode: ${config.mode})`);

    // Create helpers
    const naming = createNaming(config, stage);
    const tags = createTags(config, stage);

    // Determine domains
    const frontendDomain = config.frontend?.cloudfrontDomain || `dashboard-${stage}.example.com`;
    const apiDomain = getApiDomain(config);

    // Create DNS provider if cross-account
    const dnsProvider = config.apiGateway?.route53Profile
      ? new aws.Provider("DnsProvider", {
          region: (config.aws?.region || "eu-west-3") as aws.Region,
          profile: config.apiGateway.route53Profile,
        })
      : undefined;

    // ==========================================================================
    // Create Resources
    // ==========================================================================

    // 1. DynamoDB tables
    const tables = createDynamoDBTables(config, naming, tags);

    // 2. KMS key for auth encryption
    const kmsKey = config.auth?.enabled !== false ? createKmsKey(config, naming, tags) : undefined;

    // 3. API Certificate (if custom domain with cross-account DNS)
    const apiCertificateArn = apiDomain && dnsProvider
      ? createApiCertificate(config, tags, apiDomain, dnsProvider)
      : undefined;

    // 4. API Gateway
    const api = createApiGateway(config, naming, tags, frontendDomain, apiDomain, apiCertificateArn);

    // 5. Lambda functions (with KMS key for auth encryption)
    const lambdas = createLambdaFunctions(config, naming, tags, tables, frontendDomain, kmsKey);

    // 6. Setup API Gateway authorizer and routes
    const authorizer = setupAuthorizer(api, lambdas.authorizer);
    setupRoutes(api, lambdas, authorizer);

    // 7. Create DNS record for API (if cross-account)
    if (apiDomain && dnsProvider && apiCertificateArn) {
      createApiDnsRecord(config, api, apiDomain, dnsProvider);
    }

    // ==========================================================================
    // Frontend Deployment (managed mode only)
    // ==========================================================================
    let frontendOutput = {
      url: api.url as unknown as string,
      cloudfrontId: "",
      s3Bucket: "",
    };

    if (config.mode === "managed" && config.frontend) {
      // Build frontend with API URL
      await buildFrontend(apiDomain);

      // Deploy to S3 and invalidate CloudFront
      frontendOutput = await deployFrontendToS3(config, stage);
    }

    // ==========================================================================
    // Outputs
    // ==========================================================================
    return {
      url: frontendOutput.url || api.url,
      cloudfrontId: frontendOutput.cloudfrontId,
      apiUrl: api.url,
      ...(apiDomain && { apiDomain: `https://${apiDomain}` }),
      s3Bucket: frontendOutput.s3Bucket,
      ...(kmsKey && { kmsKeyArn: kmsKey.arn, kmsKeyManaged: kmsKey.managed }),
    };
  },
});
