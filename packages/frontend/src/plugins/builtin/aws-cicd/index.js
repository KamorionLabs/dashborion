/**
 * AWS CI/CD Plugin - Frontend
 *
 * Provides pages and widgets for monitoring CI/CD pipelines.
 */

import { lazy } from 'react';
import { GitBranch, Play, History } from 'lucide-react';

const PipelinesPage = lazy(() => import('./pages/PipelinesPage'));
const PipelineDetailPage = lazy(() => import('./pages/PipelineDetailPage'));

export const awsCicdPlugin = {
  id: 'aws-cicd',
  name: 'AWS CI/CD',
  version: '0.1.0',

  pages: [
    {
      id: 'cicd-pipelines',
      path: '/:project/:env/pipelines',
      title: 'Pipelines',
      component: PipelinesPage,
      icon: GitBranch,
      showInNav: true,
      navOrder: 20,
    },
    {
      id: 'cicd-pipeline-detail',
      path: '/:project/:env/pipelines/:pipeline',
      title: 'Pipeline Details',
      component: PipelineDetailPage,
      showInNav: false,
    },
  ],

  navItems: [
    {
      id: 'cicd-nav',
      label: 'Pipelines',
      path: '/:project/:env/pipelines',
      icon: GitBranch,
    },
  ],

  initialize: async (config) => {
    console.log('[AWS CI/CD Plugin] Initialized');
  },
};

export default awsCicdPlugin;
