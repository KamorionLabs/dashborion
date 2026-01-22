/**
 * AWS CodePipeline Configuration Component
 */
export default function CodePipelineConfig({
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
    <div>
      <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Pipeline Name</label>
      <input
        type="text"
        value={categoryConfig?.pipelineName || ''}
        onChange={(e) => updateConfig({ pipelineName: e.target.value })}
        placeholder="my-deploy-pipeline"
        className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
      />
    </div>
  );
}
