/**
 * Pipeline configuration constants
 */

export const PIPELINE_PROVIDER_TYPES = [
  { value: 'codepipeline', label: 'AWS CodePipeline' },
  { value: 'jenkins', label: 'Jenkins' },
  { value: 'argocd', label: 'ArgoCD' },
  { value: 'github-actions', label: 'GitHub Actions' },
  { value: 'azure-devops', label: 'Azure DevOps' },
];

export const PIPELINE_CATEGORY_LABELS = {
  build: 'Build (CI)',
  deploy: 'Deploy (CD)',
};

// Provider field definitions (for providers without custom components)
export const PIPELINE_PROVIDER_FIELDS = {
  codepipeline: [
    { key: 'pipelineName', label: 'Pipeline Name', type: 'text', placeholder: 'my-deploy-pipeline' },
  ],
  jenkins: [
    { key: 'jobPath', label: 'Job Path', type: 'text', placeholder: 'RubixDeployment/EKS/STAGING/deploy-service' },
  ],
  argocd: [
    { key: 'appName', label: 'Application Name', type: 'text', placeholder: 'my-app-staging' },
    { key: 'project', label: 'ArgoCD Project', type: 'text', placeholder: 'default' },
  ],
  'github-actions': [
    { key: 'repo', label: 'Repository', type: 'text', placeholder: 'org/repo' },
    { key: 'workflow', label: 'Workflow', type: 'text', placeholder: 'deploy.yml' },
  ],
  'azure-devops': [
    { key: 'organization', label: 'Organization', type: 'text', placeholder: 'my-org' },
    { key: 'adoProject', label: 'Project', type: 'text', placeholder: 'MyProject' },
    { key: 'pipelineId', label: 'Pipeline ID', type: 'text', placeholder: '123' },
  ],
};
