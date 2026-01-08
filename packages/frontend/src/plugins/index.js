/**
 * Dashborion Frontend Plugin System
 *
 * Export all plugin-related utilities
 */

// Registry
export { PluginRegistry } from './PluginRegistry';

// Context and hooks
export {
  PluginProvider,
  usePlugins,
  useWidgets,
  usePluginPages,
  usePluginNav,
} from './PluginContext';

// Router
export {
  PluginRouter,
  useRouteParams,
  usePluginNavigate,
} from './PluginRouter';

// Widget rendering
export {
  WidgetRenderer,
  SingleWidget,
} from './WidgetRenderer';
