/**
 * Azure DevOps Pipeline Configuration Component
 */
export default function AzureDevOpsConfig({
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
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
      {/* Organization */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Organization</label>
        <input
          type="text"
          value={categoryConfig?.organization || ''}
          onChange={(e) => updateConfig({ organization: e.target.value })}
          placeholder="my-org"
          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
      </div>

      {/* Project */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Project</label>
        <input
          type="text"
          value={categoryConfig?.adoProject || ''}
          onChange={(e) => updateConfig({ adoProject: e.target.value })}
          placeholder="MyProject"
          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
      </div>

      {/* Pipeline ID */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Pipeline ID</label>
        <input
          type="text"
          value={categoryConfig?.pipelineId || ''}
          onChange={(e) => updateConfig({ pipelineId: e.target.value })}
          placeholder="123"
          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
        />
      </div>
    </div>
  );
}
