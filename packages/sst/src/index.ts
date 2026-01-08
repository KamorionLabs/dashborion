/**
 * @dashborion/sst
 *
 * SST Component for deploying Dashborion infrastructure dashboard
 */

export { Dashborion } from './Dashborion.js';
export type {
  DashborionArgs,
  DashborionOutputs,
  DeploymentMode,
  ExternalResources,
  AwsConfig,
  BackendConfig,
  FrontendBuildConfig,
  AuthLambdaConfig,
} from './types.js';

// Re-export config types from core for convenience
export type {
  AuthConfig,
  AuthProvider,
  SamlConfig,
  OidcConfig,
  DashborionConfig,
  ProjectConfig,
  EnvironmentConfig,
  CrossAccountRole,
  FeatureFlags,
} from '@dashborion/core';
