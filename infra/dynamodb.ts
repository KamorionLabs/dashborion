/**
 * DynamoDB tables for Dashborion
 * SST always creates and manages all tables
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig } from "./config";
import { NamingHelper } from "./naming";
import { TagsHelper } from "./tags";

/**
 * Table reference
 */
export interface TableRef {
  /** Table name */
  name: $util.Output<string>;
  /** Table ARN */
  arn: $util.Output<string>;
  /** SST resource (for linking) */
  resource: sst.aws.Dynamo;
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
  config: TableRef;
}

/**
 * Create DynamoDB tables with SST
 */
export function createDynamoDBTables(
  config: InfraConfig,
  naming: NamingHelper,
  tags: TagsHelper
): DynamoDBTables {
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

  // Config Registry table - stores projects, environments, clusters, accounts, settings
  const configTable = new sst.aws.Dynamo("ConfigTable", {
    fields: {
      pk: "string",
      sk: "string",
      projectId: "string",
    },
    primaryIndex: { hashKey: "pk", rangeKey: "sk" },
    globalIndexes: {
      "project-index": { hashKey: "projectId", rangeKey: "sk" },
    },
    transform: {
      table: {
        name: naming.table("config"),
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
    config: { name: configTable.name, arn: configTable.arn, resource: configTable },
  };
}

/**
 * Get linkable resources for Lambda functions
 */
export function getLinkableResources(tables: DynamoDBTables): sst.aws.Dynamo[] {
  return Object.values(tables).map((t) => t.resource);
}

/**
 * Get all table ARNs including GSI ARNs (for IAM permissions)
 */
export function getAllTableArns(tables: DynamoDBTables): $util.Output<string>[] {
  const arns: $util.Output<string>[] = [];
  for (const table of Object.values(tables)) {
    arns.push(table.arn);
    arns.push($interpolate`${table.arn}/index/*`);
  }
  return arns;
}
