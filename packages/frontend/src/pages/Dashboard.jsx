/**
 * Dashboard - Main Overview Page
 *
 * Displays widgets from all registered plugins.
 */
import { useWidgets } from '../plugins/PluginContext';
import WidgetRenderer from '../plugins/WidgetRenderer';
import { Activity, Clock } from 'lucide-react';

export default function Dashboard({ refreshKey }) {
  const widgets = useWidgets('dashboard');

  // Get project/env from URL or config
  const projectId = 'homebox';
  const environment = 'production';

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Dashboard</h1>
          <p className="text-gray-500">Overview of all monitored resources</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Clock size={14} />
          <span>Last refresh: {new Date().toLocaleTimeString()}</span>
        </div>
      </div>

      {widgets.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {widgets.map((widget) => (
            <WidgetRenderer
              key={widget.id}
              widget={widget}
              projectId={projectId}
              environment={environment}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12 border border-dashed border-gray-700 rounded-lg">
          <Activity size={48} className="mx-auto text-gray-600 mb-4" />
          <p className="text-gray-500">No widgets configured for this dashboard.</p>
          <p className="text-gray-600 text-sm mt-2">
            Plugins can register widgets to display summary information here.
          </p>
        </div>
      )}
    </div>
  );
}
