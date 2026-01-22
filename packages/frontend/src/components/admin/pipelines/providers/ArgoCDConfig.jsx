/**
 * ArgoCD Pipeline Configuration Component
 */
import { Search } from 'lucide-react';

export default function ArgoCDConfig({
  serviceId,
  category,
  categoryConfig,
  providerId,
  onConfigChange,
  onOpenDiscovery,
}) {
  const updateConfig = (updates) => {
    onConfigChange(serviceId, category, {
      ...categoryConfig,
      ...updates,
    });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {/* Application Name */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Application Name</label>
        <div className="flex gap-1">
          <input
            type="text"
            value={categoryConfig?.appName || ''}
            onChange={(e) => updateConfig({ appName: e.target.value })}
            placeholder="my-app-staging"
            className="flex-1 px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => onOpenDiscovery('appName')}
            className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs flex items-center gap-1"
            title="Browse ArgoCD applications"
          >
            <Search size={12} />
          </button>
        </div>
      </div>

      {/* Project */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">ArgoCD Project</label>
        <input
          type="text"
          value={categoryConfig?.project || ''}
          onChange={(e) => updateConfig({ project: e.target.value })}
          placeholder="default"
          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
      </div>
    </div>
  );
}
