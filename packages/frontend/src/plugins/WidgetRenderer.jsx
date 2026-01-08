/**
 * Widget Renderer for Dashborion Frontend
 *
 * Renders all widgets registered for a specific position.
 */

import { Suspense } from 'react';
import { useWidgets, usePlugins } from './PluginContext';

/**
 * Loading fallback for widgets
 */
function WidgetLoading({ name }) {
  return (
    <div className="animate-pulse bg-gray-800 rounded-lg p-4">
      <div className="h-4 bg-gray-700 rounded w-1/3 mb-2"></div>
      <div className="h-20 bg-gray-700 rounded"></div>
      <span className="sr-only">Loading {name}...</span>
    </div>
  );
}

/**
 * Error boundary for widgets
 */
function WidgetError({ widgetId, error }) {
  return (
    <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
      <h4 className="text-red-400 font-medium">Widget Error</h4>
      <p className="text-red-300 text-sm mt-1">
        Failed to render widget: {widgetId}
      </p>
      {error && (
        <pre className="text-xs text-red-200 mt-2 overflow-auto">
          {error.message}
        </pre>
      )}
    </div>
  );
}

/**
 * Single widget wrapper with error handling
 */
function WidgetWrapper({ widget, props }) {
  const Component = widget.component;

  if (!Component) {
    return <WidgetError widgetId={widget.id} error={new Error('No component')} />;
  }

  try {
    return (
      <Suspense fallback={<WidgetLoading name={widget.name} />}>
        <Component {...props} widgetId={widget.id} />
      </Suspense>
    );
  } catch (error) {
    return <WidgetError widgetId={widget.id} error={error} />;
  }
}

/**
 * Render all widgets for a position
 */
export function WidgetRenderer({
  position,
  projectId,
  environment,
  config = {},
  refreshKey,
  onNavigate,
  onShowDetails,
  className = '',
  itemClassName = '',
}) {
  const widgets = useWidgets(position);

  if (widgets.length === 0) {
    return null;
  }

  const widgetProps = {
    projectId,
    environment,
    config,
    refreshKey,
    onNavigate,
    onShowDetails,
  };

  return (
    <div className={className}>
      {widgets.map((widget) => (
        <div key={widget.id} className={itemClassName}>
          <WidgetWrapper
            widget={widget}
            props={{
              ...widgetProps,
              config: config[widget.pluginId] || {},
            }}
          />
        </div>
      ))}
    </div>
  );
}

/**
 * Render a single widget by ID
 */
export function SingleWidget({ widgetId, pluginId, ...props }) {
  const { getPlugin } = usePlugins();
  const plugin = getPlugin(pluginId);

  if (!plugin) {
    return <WidgetError widgetId={widgetId} error={new Error(`Plugin not found: ${pluginId}`)} />;
  }

  const widget = plugin.widgets?.find(w => w.id === widgetId);

  if (!widget) {
    return <WidgetError widgetId={widgetId} error={new Error(`Widget not found: ${widgetId}`)} />;
  }

  return <WidgetWrapper widget={widget} props={props} />;
}

export default WidgetRenderer;
