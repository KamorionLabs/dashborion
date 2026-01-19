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
 *   - npx sst deploy --stage local (LocalStack - requires docker-compose up)
 *
 * Modes:
 *   - standalone: SST creates all resources (DynamoDB, IAM roles, etc.)
 *   - managed: References existing resources created by Terraform/OpenTofu
 *
 * LocalStack:
 *   1. docker-compose up -d
 *   2. npx sst deploy --stage local
 *   3. ./scripts/seed-localstack.sh (optional: seed config data)
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

// LocalStack endpoint (default port)
const LOCALSTACK_ENDPOINT = process.env.LOCALSTACK_ENDPOINT || "http://localhost:4566";

// Build LocalStack AWS provider config
function getLocalStackProviderConfig(region: aws.Region) {
  return {
    region,
    accessKey: "test",
    secretKey: "test",
    skipCredentialsValidation: true,
    skipMetadataApiCheck: true,
    skipRegionValidation: true,
    skipRequestingAccountId: true,
    s3UsePathStyle: true,
    endpoints: [{
      apigateway: LOCALSTACK_ENDPOINT,
      apigatewayv2: LOCALSTACK_ENDPOINT,
      cloudwatch: LOCALSTACK_ENDPOINT,
      dynamodb: LOCALSTACK_ENDPOINT,
      iam: LOCALSTACK_ENDPOINT,
      kms: LOCALSTACK_ENDPOINT,
      lambda: LOCALSTACK_ENDPOINT,
      s3: LOCALSTACK_ENDPOINT,
      ssm: LOCALSTACK_ENDPOINT,
      sts: LOCALSTACK_ENDPOINT,
    }],
  };
}

export default $config({
  app(input) {
    const config = loadConfigSync();
    const isLocalStack = input?.stage === "local";
    const region = (config.aws?.region || "eu-west-3") as aws.Region;

    return {
      name: config.naming?.app || "dashborion",
      removal: input?.stage === "production" ? "retain" : "remove",
      protect: ["production"].includes(input?.stage),
      home: isLocalStack ? "local" : "aws",
      providers: {
        aws: isLocalStack
          ? getLocalStackProviderConfig(region)
          : {
              region,
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
      createSsmParameters,
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
    const isLocalStack = stage === "local";
    const configDir = getConfigDir();
    const config = loadConfig();

    // Override config for LocalStack
    if (isLocalStack) {
      config.mode = "standalone";
      config.auth = { enabled: false };
      console.log(`Deploying Dashborion to LocalStack (stage: ${stage})`);
      console.log(`  LocalStack endpoint: ${LOCALSTACK_ENDPOINT}`);
    } else {
      console.log(`Deploying Dashborion (stage: ${stage}, mode: ${config.mode})`);
    }

    // Create helpers
    const naming = createNaming(config, stage);
    const tags = createTags(config, stage);

    // Determine domains (skip for LocalStack)
    const frontendDomain = isLocalStack
      ? "localhost"
      : config.frontend?.cloudfrontDomain || `dashboard-${stage}.example.com`;
    const apiDomain = isLocalStack ? undefined : getApiDomain(config);

    // Create DNS provider if cross-account (skip for LocalStack)
    const dnsProvider = !isLocalStack && config.apiGateway?.route53Profile
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

    // 3. SSM parameters (deprecated - config now uses DynamoDB Config Registry)
    // Kept for backward compatibility during migration
    const ssmParams = createSsmParameters(config, naming, tags);

    // 4. API Certificate (if custom domain with cross-account DNS)
    const apiCertificateArn = apiDomain && dnsProvider
      ? createApiCertificate(config, tags, apiDomain, dnsProvider)
      : undefined;

    // 5. API Gateway
    const api = createApiGateway(config, naming, tags, frontendDomain, apiDomain, apiCertificateArn);

    // 6. Lambda functions (config is loaded from DynamoDB via CONFIG_TABLE_NAME)
    const lambdas = createLambdaFunctions(config, naming, tags, tables, frontendDomain, kmsKey);

    // 7. Setup API Gateway authorizers and routes
    const authorizers = {
      default: setupAuthorizer(api, lambdas.authorizer, {
        name: "DashborionAuth",
        ttl: "300 seconds",
        identitySources: ["$request.header.authorization"],
      }),
      session: setupAuthorizer(api, lambdas.authorizer, {
        name: "DashborionAuthSession",
        ttl: "0 seconds",
        identitySources: [],
      }),
    };
    setupRoutes(api, lambdas, authorizers);

    // 8. Create DNS record for API (if cross-account)
    if (apiDomain && dnsProvider && apiCertificateArn) {
      createApiDnsRecord(config, api, apiDomain, dnsProvider);
    }

    // ==========================================================================
    // Frontend Deployment (managed mode only, skip for LocalStack)
    // ==========================================================================
    let frontendOutput = {
      url: api.url as unknown as string,
      cloudfrontId: "",
      s3Bucket: "",
    };

    if (!isLocalStack && config.mode === "managed" && config.frontend) {
      // Build frontend with API URL
      await buildFrontend(apiDomain);

      // Deploy to S3 and invalidate CloudFront
      frontendOutput = await deployFrontendToS3(config, stage);
    }

    // ==========================================================================
    // Outputs
    // ==========================================================================
    if (isLocalStack) {
      // LocalStack-specific outputs
      return {
        apiUrl: api.url,
        localstackEndpoint: LOCALSTACK_ENDPOINT,
        configTable: tables.config.name,
        stateTable: tables.state.name,
        note: "Run 'npm run dev' in packages/frontend to start the frontend dev server",
      };
    }

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
