/**
 * SST Component types for Dashborion
 */

import type {
  AuthConfig,
  DashborionConfig,
  SstDeploymentConfig,
} from '@dashborion/core';
import * as pulumi from '@pulumi/pulumi';

/**
 * Deployment mode for Dashborion
 *
 * - standalone: Full deployment (S3, CloudFront, Lambda, API Gateway)
 * - semi-managed: Some resources are external (e.g., existing CloudFront)
 * - managed: All resources are external, just deploy Lambda
 */
export type DeploymentMode = 'standalone' | 'semi-managed' | 'managed';

/**
 * External resource references (for managed mode)
 */
export interface ExternalResources {
  /** S3 bucket name for frontend */
  s3Bucket?: string;
  /** S3 bucket ARN */
  s3BucketArn?: string;
  /** CloudFront distribution ID */
  cloudfrontDistributionId?: string;
  /** CloudFront domain */
  cloudfrontDomain?: string;
  /** ACM certificate ARN (must be in us-east-1) */
  certificateArn?: string;
  /** CloudFront Origin Access Control ID */
  originAccessControlId?: string;
  /** API Gateway ID */
  apiGatewayId?: string;
  /** API Gateway URL */
  apiGatewayUrl?: string;
  /** Lambda execution role ARN */
  lambdaRoleArn?: string;
}

/**
 * AWS configuration
 */
export interface AwsConfig {
  /** AWS region */
  region?: string;
  /** AWS profile to use */
  profile?: string;
}

/**
 * Backend configuration (Python Lambda)
 */
export interface BackendConfig {
  /** Path to the backend Python code */
  codePath?: string;
  /** Lambda memory size in MB */
  memorySize?: number;
  /** Lambda timeout in seconds */
  timeout?: number;
  /** Additional environment variables */
  environment?: Record<string, string>;
}

/**
 * Auth Lambda@Edge configuration
 */
export interface AuthLambdaConfig {
  /** Path to the auth Lambda code */
  codePath?: string;
  /** Cookie name for session */
  cookieName?: string;
}

/**
 * Frontend build configuration
 */
export interface FrontendBuildConfig {
  /** Path to the frontend build output */
  distPath?: string;
  /** Custom build command */
  buildCommand?: string;
}

/**
 * Dashborion SST Component arguments
 */
export interface DashborionArgs {
  /** Domain for the dashboard */
  domain: string;

  /** Authentication configuration */
  auth: AuthConfig;

  /** Dashborion configuration (projects, environments, features) */
  config: DashborionConfig;

  /** Deployment mode */
  mode?: DeploymentMode;

  /** AWS configuration */
  aws?: AwsConfig;

  /** External resources (for managed mode) */
  external?: ExternalResources;

  /** Backend configuration */
  backend?: BackendConfig;

  /** Auth Lambda@Edge configuration */
  authLambda?: AuthLambdaConfig;

  /** Frontend build configuration */
  frontendBuild?: FrontendBuildConfig;

  /** Path to IDP metadata file (for SAML) */
  idpMetadataPath?: string;
}

/**
 * Dashborion component outputs
 */
export interface DashborionOutputs {
  /** Dashboard URL */
  url: pulumi.Output<string>;
  /** CloudFront distribution ID */
  cloudfrontId: pulumi.Output<string>;
  /** API Gateway URL */
  apiUrl: pulumi.Output<string>;
  /** S3 bucket name */
  s3Bucket: pulumi.Output<string>;
}
