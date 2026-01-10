/**
 * DynamoDB tables for Dashborion
 * Supports both creating new tables (standalone) and referencing existing ones (managed)
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig, useExistingDynamoDB } from "./config";
import { NamingHelper } from "./naming";
import { TagsHelper } from "./tags";

/**
 * Table reference (either SST Dynamo or existing table info)
 */
export interface TableRef {
  /** Table name */
  name: $util.Output<string> | string;
  /** Table ARN */
  arn: $util.Output<string> | string;
  /** Whether this is an SST-managed resource (for linking) */
  resource?: sst.aws.Dynamo;
}

/**
 * All DynamoDB tables
 */
export interface DynamoDBTables {
  tokens: TableRef;
  deviceCodes: TableRef;
  users: TableRef;
  groups: TableRef;
  permissions: TableRef;
  audit: TableRef;
}

/**
 * Create or reference DynamoDB tables
 */
export function createDynamoDBTables(
  config: InfraConfig,
  naming: NamingHelper,
  tags: TagsHelper
): DynamoDBTables {
  const useExisting = useExistingDynamoDB(config);
  const existingTables = config.managed?.dynamodb;
  const region = config.aws?.region || "eu-west-3";

  // Helper to get account ID from config or use placeholder
  const getAccountId = (): string => {
    // In managed mode, we can extract account from existing table ARNs or use a placeholder
    if (existingTables?.tokensTable) {
      // Try to get from first project's environment
      const firstProject = Object.values(config.projects || {})[0];
      const firstEnv = Object.values(firstProject?.environments || {})[0];
      return firstEnv?.accountId || "ACCOUNT_ID";
    }
    return "ACCOUNT_ID";
  };

  if (useExisting && existingTables) {
    console.log("Using existing DynamoDB tables from config");
    const accountId = getAccountId();

    // Reference existing tables
    return {
      tokens: {
        name: existingTables.tokensTable!,
        arn: `arn:aws:dynamodb:${region}:${accountId}:table/${existingTables.tokensTable}`,
      },
      deviceCodes: {
        name: existingTables.deviceCodesTable!,
        arn: `arn:aws:dynamodb:${region}:${accountId}:table/${existingTables.deviceCodesTable}`,
      },
      users: {
        name: existingTables.usersTable!,
        arn: `arn:aws:dynamodb:${region}:${accountId}:table/${existingTables.usersTable}`,
      },
      groups: {
        name: existingTables.groupsTable!,
        arn: `arn:aws:dynamodb:${region}:${accountId}:table/${existingTables.groupsTable}`,
      },
      permissions: {
        name: existingTables.permissionsTable!,
        arn: `arn:aws:dynamodb:${region}:${accountId}:table/${existingTables.permissionsTable}`,
      },
      audit: {
        name: existingTables.auditTable!,
        arn: `arn:aws:dynamodb:${region}:${accountId}:table/${existingTables.auditTable}`,
      },
    };
  }

  // Create new tables with SST
  console.log("Creating DynamoDB tables with SST");

  const tokensTable = new sst.aws.Dynamo("TokensTable", {
    fields: {
      pk: "string",
      sk: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    ttl: "ttl",
    transform: {
      table: {
        name: naming.table("tokens"),
        tags: tags.component("dynamodb"),
      },
    },
  });

  const deviceCodesTable = new sst.aws.Dynamo("DeviceCodesTable", {
    fields: {
      pk: "string",
      sk: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    ttl: "ttl",
    transform: {
      table: {
        name: naming.table("device-codes"),
        tags: tags.component("dynamodb"),
      },
    },
  });

  const usersTable = new sst.aws.Dynamo("UsersTable", {
    fields: {
      pk: "string",
      sk: "string",
      gsi1pk: "string",
      gsi1sk: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    globalIndexes: {
      "role-index": { hashKey: "gsi1pk", rangeKey: "gsi1sk" },
    },
    transform: {
      table: {
        name: naming.table("users"),
        tags: tags.component("dynamodb"),
      },
    },
  });

  const groupsTable = new sst.aws.Dynamo("GroupsTable", {
    fields: {
      pk: "string",
      sk: "string",
      gsi1pk: "string",
      gsi1sk: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    globalIndexes: {
      "sso-group-index": { hashKey: "gsi1pk", rangeKey: "gsi1sk" },
    },
    transform: {
      table: {
        name: naming.table("groups"),
        tags: tags.component("dynamodb"),
      },
    },
  });

  const permissionsTable = new sst.aws.Dynamo("PermissionsTable", {
    fields: {
      pk: "string",
      sk: "string",
      gsi1pk: "string",
      gsi1sk: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    globalIndexes: {
      "project-env-index": { hashKey: "gsi1pk", rangeKey: "gsi1sk" },
    },
    ttl: "ttl",
    transform: {
      table: {
        name: naming.table("permissions"),
        tags: tags.component("dynamodb"),
      },
    },
  });

  const auditTable = new sst.aws.Dynamo("AuditTable", {
    fields: {
      pk: "string",
      sk: "string",
      gsi1pk: "string",
      gsi1sk: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    globalIndexes: {
      "action-index": { hashKey: "gsi1pk", rangeKey: "gsi1sk" },
    },
    ttl: "ttl",
    transform: {
      table: {
        name: naming.table("audit"),
        tags: tags.component("dynamodb"),
      },
    },
  });

  return {
    tokens: { name: tokensTable.name, arn: tokensTable.arn, resource: tokensTable },
    deviceCodes: { name: deviceCodesTable.name, arn: deviceCodesTable.arn, resource: deviceCodesTable },
    users: { name: usersTable.name, arn: usersTable.arn, resource: usersTable },
    groups: { name: groupsTable.name, arn: groupsTable.arn, resource: groupsTable },
    permissions: { name: permissionsTable.name, arn: permissionsTable.arn, resource: permissionsTable },
    audit: { name: auditTable.name, arn: auditTable.arn, resource: auditTable },
  };
}

/**
 * Get linkable resources (only SST-managed tables)
 */
export function getLinkableResources(tables: DynamoDBTables): sst.aws.Dynamo[] {
  return Object.values(tables)
    .filter((t) => t.resource)
    .map((t) => t.resource!);
}

/**
 * Get all table ARNs (for IAM permissions)
 */
export function getTableArns(tables: DynamoDBTables): ($util.Output<string> | string)[] {
  return Object.values(tables).map((t) => t.arn);
}

/**
 * Get all table ARNs including GSI ARNs (for IAM permissions)
 */
export function getAllTableArns(tables: DynamoDBTables): ($util.Output<string> | string)[] {
  const arns: ($util.Output<string> | string)[] = [];
  for (const table of Object.values(tables)) {
    arns.push(table.arn);
    // Add GSI ARN pattern
    if (typeof table.arn === "string") {
      arns.push(`${table.arn}/index/*`);
    } else {
      arns.push($interpolate`${table.arn}/index/*`);
    }
  }
  return arns;
}
