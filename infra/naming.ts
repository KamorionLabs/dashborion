/**
 * Resource naming helper for Dashborion
 * Generates resource names based on naming configuration
 */

import { InfraConfig, NamingConfig } from "./config";

export interface NamingHelper {
  /** Generate Lambda function name */
  lambda: (role: string) => string;
  /** Generate Lambda Layer name */
  layer: (role: string) => string;
  /** Generate DynamoDB table name */
  table: (role: string) => string;
  /** Generate API Gateway name */
  api: (role?: string) => string;
  /** Generate IAM Role name */
  role: (role: string) => string;
  /** Generate S3 bucket name */
  bucket: (role: string) => string;
  /** Get raw config values */
  config: {
    app: string;
    owner: string;
    stage: string;
    prefixes: NamingConfig["prefixes"];
  };
}

/**
 * Replace placeholders in pattern string
 */
function applyPattern(
  pattern: string,
  vars: { app: string; stage: string; role: string; owner: string; prefix: string }
): string {
  return pattern
    .replace(/\{app\}/g, vars.app)
    .replace(/\{stage\}/g, vars.stage)
    .replace(/\{role\}/g, vars.role)
    .replace(/\{owner\}/g, vars.owner)
    .replace(/\{prefix\}/g, vars.prefix)
    .replace(/^-+|-+$/g, "")  // Remove leading/trailing dashes
    .replace(/-+/g, "-");      // Collapse multiple dashes
}

/**
 * Create naming helper from config
 */
export function createNaming(config: InfraConfig, stage: string): NamingHelper {
  const naming = config.naming || {};
  const app = naming.app || "dashborion";
  const owner = naming.owner || "";
  const prefixes = naming.prefixes || {};
  const patterns = naming.patterns || {};

  const vars = (role: string, prefix?: string) => ({
    app,
    stage,
    role,
    owner,
    prefix: prefix || "",
  });

  return {
    lambda: (role: string): string => {
      if (naming.convention === "custom" && patterns.lambda) {
        return applyPattern(patterns.lambda, vars(role, prefixes.lambda));
      }
      // Default pattern with optional prefix
      if (prefixes.lambda) {
        return `${prefixes.lambda}-${app}-${role}-${stage}`;
      }
      return `${app}-${stage}-${role}`;
    },

    layer: (role: string): string => {
      if (prefixes.layer) {
        return `${prefixes.layer}-${app}-${role}`;
      }
      return `${app}-${role}-layer`;
    },

    table: (role: string): string => {
      if (naming.convention === "custom" && patterns.table) {
        return applyPattern(patterns.table, vars(role, prefixes.table));
      }
      if (prefixes.table) {
        return `${prefixes.table}-${app}-${stage}-${role}`;
      }
      return `${app}-${stage}-${role}`;
    },

    api: (role: string = "api"): string => {
      if (naming.convention === "custom" && patterns.api) {
        return applyPattern(patterns.api, vars(role, prefixes.api));
      }
      if (prefixes.api) {
        return `${prefixes.api}-${app}-${stage}-${role}`;
      }
      return `${app}-${stage}-${role}`;
    },

    role: (role: string): string => {
      if (prefixes.role) {
        return `${prefixes.role}-${app}-${stage}-${role}`;
      }
      return `${app}-${stage}-${role}`;
    },

    bucket: (role: string): string => {
      if (prefixes.bucket) {
        return `${prefixes.bucket}-${app}-${stage}-${role}`;
      }
      return `${app}-${stage}-${role}`;
    },

    config: {
      app,
      owner,
      stage,
      prefixes,
    },
  };
}
