/**
 * AWS Infrastructure Plugin - Frontend
 *
 * Provides pages and widgets for monitoring AWS infrastructure
 * (ALB, RDS, ElastiCache, CloudFront, etc.)
 */

import { lazy } from 'react';
import { Globe, Database, Server, Shield } from 'lucide-react';

const InfrastructurePage = lazy(() => import('./pages/InfrastructurePage'));
const LoadBalancersPage = lazy(() => import('./pages/LoadBalancersPage'));
const DatabasesPage = lazy(() => import('./pages/DatabasesPage'));
const CachePage = lazy(() => import('./pages/CachePage'));

export const awsInfraPlugin = {
  id: 'aws-infra',
  name: 'AWS Infrastructure',
  version: '0.1.0',

  pages: [
    {
      id: 'infra-overview',
      path: '/:project/:env/infrastructure',
      title: 'Infrastructure',
      component: InfrastructurePage,
      icon: Server,
      showInNav: true,
      navOrder: 30,
    },
    {
      id: 'infra-alb',
      path: '/:project/:env/infrastructure/load-balancers',
      title: 'Load Balancers',
      component: LoadBalancersPage,
      showInNav: false,
    },
    {
      id: 'infra-databases',
      path: '/:project/:env/infrastructure/databases',
      title: 'Databases',
      component: DatabasesPage,
      showInNav: false,
    },
    {
      id: 'infra-cache',
      path: '/:project/:env/infrastructure/cache',
      title: 'Cache',
      component: CachePage,
      showInNav: false,
    },
  ],

  navItems: [
    {
      id: 'infra-nav',
      label: 'Infrastructure',
      path: '/:project/:env/infrastructure',
      icon: Server,
    },
  ],

  initialize: async (config) => {
    console.log('[AWS Infrastructure Plugin] Initialized');
  },
};

export default awsInfraPlugin;
