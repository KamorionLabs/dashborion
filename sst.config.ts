/// <reference path="./.sst/platform/config.d.ts" />

/**
 * SST Configuration for Dashborion
 *
 * This simplified configuration uses the @dashborion/sst component.
 *
 * Configuration:
 *   - Set DASHBORION_CONFIG_DIR env var to external config directory
 *   - Or create infra.config.json from infra.config.example.json
 *
 * Deployment:
 *   - npx sst dev (development with live reload)
 *   - npx sst deploy --stage homebox (production)
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
    provider?: "saml" | "oidc" | "none";
    saml?: {
      entityId: string;
      idpMetadataFile?: string;
      idpMetadataUrl?: string;
      acsPath?: string;
      metadataPath?: string;
    };
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
        aws: config.aws?.profile ? { profile: config.aws.profile } : {},
      },
    };
  },
  async run() {
    // Dynamic imports inside run() as required by SST v3
    const { Dashborion } = await import("@dashborion/sst");
    const fs = await import("fs");
    const path = await import("path");

    const stage = $app.stage;
    const configDir = getConfigDir();
    const config = loadInfraConfigSync();

    console.log(`Deploying Dashborion (stage: ${stage}, mode: ${config.mode})`);

    // Load IDP metadata from file if configured
    let idpMetadataPath: string | undefined;
    if (config.auth?.saml?.idpMetadataFile) {
      idpMetadataPath = path.join(configDir, config.auth.saml.idpMetadataFile);
    }

    // Convert cross-account roles
    const crossAccountRoles: Record<string, { readRoleArn: string; actionRoleArn?: string }> = {};
    if (config.crossAccountRoles) {
      for (const [accountId, role] of Object.entries(config.crossAccountRoles)) {
        crossAccountRoles[accountId] = {
          readRoleArn: role.readRoleArn,
          actionRoleArn: role.actionRoleArn,
        };
      }
    }

    // Convert projects
    const projects: Record<string, { displayName: string; environments: Record<string, any> }> = {};
    if (config.projects) {
      for (const [id, project] of Object.entries(config.projects)) {
        const environments: Record<string, any> = {};
        for (const [envId, env] of Object.entries(project.environments)) {
          environments[envId] = {
            accountId: env.accountId,
            region: env.region || config.aws?.region || "eu-west-3",
            clusterName: env.clusterName,
            namespace: env.namespace,
          };
        }
        projects[id] = {
          displayName: project.displayName,
          environments,
        };
      }
    }

    // Build auth config
    type AuthProvider = "saml" | "oidc" | "none";
    const auth: {
      provider: AuthProvider;
      saml?: {
        entityId: string;
        idpMetadataUrl?: string;
        acsPath?: string;
        metadataPath?: string;
      };
    } = {
      provider: (config.auth?.provider || "none") as AuthProvider,
    };

    if (config.auth?.provider === "saml" && config.auth.saml) {
      auth.saml = {
        entityId: config.auth.saml.entityId,
        idpMetadataUrl:
          config.auth.saml.idpMetadataUrl ||
          (idpMetadataPath ? `file://${idpMetadataPath}` : undefined),
        acsPath: config.auth.saml.acsPath || "/saml/acs",
        metadataPath: config.auth.saml.metadataPath || "/saml/metadata",
      };
    }

    // Create Dashborion infrastructure
    const dashboard = new Dashborion("Dashboard", {
      domain: config.frontend?.cloudfrontDomain || `dashboard-${stage}.example.com`,
      auth,
      config: {
        region: config.aws?.region || "eu-west-3",
        projects,
        crossAccountRoles,
        features: {
          ecs: true,
          pipelines: true,
          infrastructure: true,
        },
      },
      mode: config.mode,
      aws: config.aws,
      external: config.frontend
        ? {
            s3Bucket: config.frontend.s3Bucket,
            s3BucketArn: config.frontend.s3BucketArn,
            cloudfrontDistributionId: config.frontend.cloudfrontDistributionId,
            cloudfrontDomain: config.frontend.cloudfrontDomain,
            certificateArn: config.frontend.certificateArn,
            originAccessControlId: config.frontend.originAccessControlId,
            apiGatewayId: config.apiGateway?.id,
            apiGatewayUrl: config.apiGateway?.url,
            lambdaRoleArn: config.lambda?.roleArn,
          }
        : undefined,
      backend: {
        codePath: "./packages/backend/src",
        memorySize: 256,
        timeout: 30,
      },
      frontendBuild: {
        distPath: "./packages/frontend/dist",
      },
      idpMetadataPath,
    });

    return {
      url: dashboard.url,
      cloudfrontId: dashboard.cloudfrontId,
      apiUrl: dashboard.apiUrl,
      s3Bucket: dashboard.s3Bucket,
    };
  },
});
