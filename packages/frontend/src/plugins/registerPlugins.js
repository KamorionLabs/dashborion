/**
 * Plugin Registration
 *
 * Registers all frontend plugins with the PluginRegistry.
 * This is called once at application startup.
 */

import { PluginRegistry } from './PluginRegistry';

// Import built-in plugins
// These will be moved to separate packages later
import { awsEcsPlugin } from './builtin/aws-ecs';
import { awsCicdPlugin } from './builtin/aws-cicd';
import { awsInfraPlugin } from './builtin/aws-infra';

/**
 * Register all plugins
 */
export function registerPlugins() {
  // Register built-in plugins
  PluginRegistry.register(awsEcsPlugin);
  PluginRegistry.register(awsCicdPlugin);
  PluginRegistry.register(awsInfraPlugin);

  console.log('[Dashborion] Registered plugins:', PluginRegistry.getPlugins().map(p => p.id));
}

export default registerPlugins;
