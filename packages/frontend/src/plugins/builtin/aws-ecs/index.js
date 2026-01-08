/**
 * AWS ECS Plugin - Frontend
 *
 * Provides pages and widgets for monitoring ECS services.
 */

import { lazy } from 'react';
import { Server, Box, Activity, ListTodo } from 'lucide-react';

// Lazy load pages for code splitting
const ServicesPage = lazy(() => import('./pages/ServicesPage'));
const ServiceDetailPage = lazy(() => import('./pages/ServiceDetailPage'));
const ServiceLogsPage = lazy(() => import('./pages/ServiceLogsPage'));
const ServiceTasksPage = lazy(() => import('./pages/ServiceTasksPage'));

// Lazy load widgets
const ServiceCardWidget = lazy(() => import('./widgets/ServiceCardWidget'));
const ServiceStatusWidget = lazy(() => import('./widgets/ServiceStatusWidget'));

/**
 * AWS ECS Frontend Plugin Definition
 */
export const awsEcsPlugin = {
  id: 'aws-ecs',
  name: 'AWS ECS',
  version: '0.1.0',

  // Pages provided by this plugin
  pages: [
    {
      id: 'ecs-services',
      path: '/:project/:env/services',
      title: 'Services',
      component: ServicesPage,
      icon: Server,
      showInNav: true,
      navOrder: 10,
    },
    {
      id: 'ecs-service-detail',
      path: '/:project/:env/services/:service',
      title: 'Service Details',
      component: ServiceDetailPage,
      showInNav: false,
    },
    {
      id: 'ecs-service-logs',
      path: '/:project/:env/services/:service/logs',
      title: 'Service Logs',
      component: ServiceLogsPage,
      showInNav: false,
    },
    {
      id: 'ecs-service-tasks',
      path: '/:project/:env/services/:service/tasks',
      title: 'Service Tasks',
      component: ServiceTasksPage,
      showInNav: false,
    },
  ],

  // Widgets provided by this plugin
  widgets: [
    {
      id: 'ecs-service-card',
      name: 'Service Card',
      component: ServiceCardWidget,
      positions: ['dashboard'],
      priority: 10,
    },
    {
      id: 'ecs-service-status',
      name: 'Service Status',
      component: ServiceStatusWidget,
      positions: ['service-detail', 'sidebar'],
      priority: 5,
    },
  ],

  // Navigation items
  navItems: [
    {
      id: 'ecs-nav',
      label: 'Services',
      path: '/:project/:env/services',
      icon: Server,
      children: [
        {
          id: 'ecs-nav-tasks',
          label: 'Tasks',
          path: '/:project/:env/services?view=tasks',
          icon: ListTodo,
        },
      ],
    },
  ],

  // Lifecycle hooks
  initialize: async (config) => {
    console.log('[AWS ECS Plugin] Initialized with config:', Object.keys(config));
  },
};

export default awsEcsPlugin;
