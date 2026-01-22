/**
 * Pipeline Provider Configuration Components
 */
import JenkinsConfig from './JenkinsConfig';
import ArgoCDConfig from './ArgoCDConfig';
import CodePipelineConfig from './CodePipelineConfig';
import GitHubActionsConfig from './GitHubActionsConfig';
import AzureDevOpsConfig from './AzureDevOpsConfig';

export {
  JenkinsConfig,
  ArgoCDConfig,
  CodePipelineConfig,
  GitHubActionsConfig,
  AzureDevOpsConfig,
};

/**
 * Get the appropriate config component for a provider
 */
export function getProviderConfigComponent(provider) {
  const components = {
    jenkins: JenkinsConfig,
    argocd: ArgoCDConfig,
    codepipeline: CodePipelineConfig,
    'github-actions': GitHubActionsConfig,
    'azure-devops': AzureDevOpsConfig,
  };
  return components[provider] || null;
}
