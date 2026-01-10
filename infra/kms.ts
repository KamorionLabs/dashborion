/**
 * KMS Key for Dashborion authentication encryption
 *
 * Used to encrypt:
 * - Session data in DynamoDB
 * - Token metadata (email, permissions)
 *
 * In standalone mode: SST creates the key
 * In semi-managed/managed mode: Use external key from config
 */

/// <reference path="../.sst/platform/config.d.ts" />

import { InfraConfig } from "./config";
import { NamingHelper } from "./naming";
import { TagsHelper } from "./tags";

/**
 * KMS key reference
 */
export interface KmsKeyRef {
  arn: $util.Output<string> | string;
  keyId: $util.Output<string> | string;
  /** True if SST manages this key */
  managed: boolean;
}

/**
 * Check if we should use an existing KMS key
 */
export function useExistingKmsKey(config: InfraConfig): boolean {
  return (config.mode === "managed" || config.mode === "semi-managed") && !!config.auth?.kmsKeyArn;
}

/**
 * Create or reference KMS key for authentication encryption
 */
export function createKmsKey(
  config: InfraConfig,
  naming: NamingHelper,
  tags: TagsHelper
): KmsKeyRef {
  // Use existing key in managed/semi-managed mode if specified
  if (useExistingKmsKey(config)) {
    const kmsKeyArn = config.auth!.kmsKeyArn!;
    console.log(`Using existing KMS key: ${kmsKeyArn}`);

    // Extract key ID from ARN
    // ARN format: arn:aws:kms:region:account:key/key-id
    const keyId = kmsKeyArn.split('/').pop() || kmsKeyArn;

    return {
      arn: kmsKeyArn,
      keyId: keyId,
      managed: false,
    };
  }

  // In managed/semi-managed mode, KMS key must be provided via Terraform
  if (config.mode === "managed" || config.mode === "semi-managed") {
    throw new Error(
      `KMS key is required in ${config.mode} mode. ` +
      `Please create the key with Terraform and add 'auth.kmsKeyArn' to infra.config.json.`
    );
  }

  // Create new key in standalone mode only
  console.log("Creating KMS key with SST");
  // Build alias using app and stage from naming config
  const { app, stage } = naming.config;
  const keyAlias = `${app}-${stage}-auth-key`;

  const key = new aws.kms.Key("AuthEncryptionKey", {
    description: "Dashborion authentication data encryption key",
    enableKeyRotation: true,
    deletionWindowInDays: 7,
    tags: {
      ...tags.component("kms"),
      Purpose: "auth-encryption",
    },
  });

  new aws.kms.Alias("AuthEncryptionKeyAlias", {
    name: `alias/${keyAlias}`,
    targetKeyId: key.keyId,
  });

  return {
    arn: key.arn,
    keyId: key.keyId,
    managed: true,
  };
}

/**
 * Get KMS permissions for Lambda functions
 */
export function getKmsPermissions(kmsKey: KmsKeyRef): {
  actions: string[];
  resources: ($util.Output<string> | string)[];
}[] {
  return [
    {
      actions: ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"],
      resources: [kmsKey.arn],
    },
  ];
}
