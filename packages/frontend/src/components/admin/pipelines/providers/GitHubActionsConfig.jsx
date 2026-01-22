/**
 * GitHub Actions Pipeline Configuration Component
 */
export default function GitHubActionsConfig({
  serviceId,
  category,
  categoryConfig,
  onConfigChange,
}) {
  const updateConfig = (updates) => {
    onConfigChange(serviceId, category, {
      ...categoryConfig,
      ...updates,
    });
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {/* Repository */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Repository</label>
        <input
          type="text"
          value={categoryConfig?.repo || ''}
          onChange={(e) => updateConfig({ repo: e.target.value })}
          placeholder="org/repo"
          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
      </div>

      {/* Workflow */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Workflow</label>
        <input
          type="text"
          value={categoryConfig?.workflow || ''}
          onChange={(e) => updateConfig({ workflow: e.target.value })}
          placeholder="deploy.yml"
          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
      </div>
    </div>
  );
}
