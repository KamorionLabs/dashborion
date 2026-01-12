/**
 * SSM Parameter Store for large configuration values
 *
 * Lambda environment variables are limited to 4KB total.
 * For configs that exceed this limit (PROJECTS, CROSS_ACCOUNT_ROLES),
 * we store them in SSM Parameter Store and load at runtime.
 *
 * Structure:
 *   {prefix}/projects/{project-id}  - One parameter per project
 *   {prefix}/cross-account-roles    - Cross-account IAM roles
 *
 * The prefix is configurable via config.ssm.prefix (default: /dashborion/{stage})
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig } from "./config";
import { NamingHelper } from "./naming";
import { TagsHelper } from "./tags";

/**
 * SSM Parameter references
 */
export interface SsmParameters {
  projectParams: aws.ssm.Parameter[];
  crossAccountRolesParam: aws.ssm.Parameter;
  prefix: string;
}

/**
 * Build project JSON for a single project
 */
function buildProjectJson(
  id: string,
  project: any,
  defaultRegion: string
): string {
  const environments: Record<string, any> = {};
  if (project.environments) {
    for (const [envId, env] of Object.entries(project.environments)) {
      if (envId.startsWith("_") || typeof env !== "object" || env === null) continue;
      environments[envId] = {
        accountId: (env as any).accountId,
        region: (env as any).region || defaultRegion,
        clusterName: (env as any).clusterName,
        namespace: (env as any).namespace,
        services: (env as any).services || [],
      };
    }
  }
  return JSON.stringify({
    id,
    displayName: project.displayName,
    environments,
    idpGroupMapping: project.idpGroupMapping,
  });
}

/**
 * Build the cross-account roles JSON for SSM
 */
function buildCrossAccountRolesJson(config: InfraConfig): string {
  const crossAccountRoles: Record<string, { readRoleArn: string; actionRoleArn?: string }> = {};
  if (config.crossAccountRoles) {
    for (const [accountId, role] of Object.entries(config.crossAccountRoles)) {
      if (accountId.startsWith("_") || typeof role !== "object" || role === null) continue;
      crossAccountRoles[accountId] = {
        readRoleArn: role.readRoleArn,
        actionRoleArn: role.actionRoleArn,
      };
    }
  }
  return JSON.stringify(crossAccountRoles);
}

/**
 * Get SSM prefix from config or use default
 */
export function getSsmPrefix(config: InfraConfig): string {
  return config.ssm?.prefix || `/dashborion/${$app.stage}`;
}

/**
 * Create SSM parameters for large config values
 */
export function createSsmParameters(
  config: InfraConfig,
  naming: NamingHelper,
  tags: TagsHelper
): SsmParameters {
  const prefix = getSsmPrefix(config);
  const defaultRegion = config.aws?.region || "eu-west-3";

  // Create one parameter per project
  const projectParams: aws.ssm.Parameter[] = [];
  if (config.projects) {
    for (const [id, project] of Object.entries(config.projects)) {
      if (id.startsWith("_") || typeof project !== "object" || project === null) continue;

      const projectJson = buildProjectJson(id, project, defaultRegion);
      const param = new aws.ssm.Parameter(`ConfigProject_${id}`, {
        name: `${prefix}/projects/${id}`,
        type: "String",
        tier: projectJson.length > 4096 ? "Advanced" : "Standard",
        value: projectJson,
        description: `Dashborion project: ${(project as any).displayName || id}`,
        tags: tags.component("ssm"),
      });
      projectParams.push(param);
    }
  }

  // Cross-account roles parameter
  const crossAccountRolesJson = buildCrossAccountRolesJson(config);
  const crossAccountRolesParam = new aws.ssm.Parameter("ConfigCrossAccountRoles", {
    name: `${prefix}/cross-account-roles`,
    type: "String",
    tier: crossAccountRolesJson.length > 4096 ? "Advanced" : "Standard",
    value: crossAccountRolesJson,
    description: "Dashborion cross-account IAM roles",
    tags: tags.component("ssm"),
  });

  return {
    projectParams,
    crossAccountRolesParam,
    prefix,
  };
}

/**
 * Get SSM read permissions for Lambda
 */
export function getSsmReadPermissions(prefix: string): {
  actions: string[];
  resources: string[];
}[] {
  return [{
    actions: ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"],
    resources: [`arn:aws:ssm:*:*:parameter${prefix}/*`],
  }];
}
