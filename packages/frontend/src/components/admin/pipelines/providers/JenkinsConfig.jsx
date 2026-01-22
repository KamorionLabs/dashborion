/**
 * Jenkins Pipeline Configuration Component
 *
 * Handles Jenkins-specific pipeline configuration including:
 * - Job path selection with discovery browser
 * - Dynamic parameter configuration based on job definition
 */
import { useState } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { fetchWithRetry } from '../../../../utils/fetch';

export default function JenkinsConfig({
  serviceId,
  category,
  categoryConfig,
  serviceConfig,
  providerId,
  onConfigChange,
  onOpenDiscovery,
}) {
  const [loadingParams, setLoadingParams] = useState(false);

  const updateConfig = (updates) => {
    onConfigChange(serviceId, category, {
      ...categoryConfig,
      ...updates,
    });
  };

  const updateParameter = (paramName, value) => {
    updateConfig({
      parameters: {
        ...categoryConfig?.parameters,
        [paramName]: value,
      },
    });
  };

  const fetchJobParameters = async () => {
    if (!categoryConfig?.jobPath || !providerId) return;

    setLoadingParams(true);
    try {
      const params = new URLSearchParams({ providerId });
      const response = await fetchWithRetry(`/api/pipelines/jenkins/job/${categoryConfig.jobPath}?${params}`);
      if (response.ok) {
        const data = await response.json();
        if (data.parameters && data.parameters.length > 0) {
          updateConfig({
            parameterDefinitions: data.parameters,
            parameters: categoryConfig?.parameters ||
              data.parameters.reduce((acc, param) => {
                acc[param.name] = param.defaultValue || '';
                return acc;
              }, {}),
          });
        }
      }
    } catch (err) {
      console.error('Failed to fetch job parameters:', err);
    } finally {
      setLoadingParams(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Job Path */}
      <div>
        <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Job Path</label>
        <div className="flex gap-1">
          <input
            type="text"
            value={categoryConfig?.jobPath || ''}
            onChange={(e) => updateConfig({ jobPath: e.target.value })}
            placeholder="RubixDeployment/EKS/STAGING/deploy-service"
            className="flex-1 px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={() => onOpenDiscovery('jobPath')}
            className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs flex items-center gap-1"
            title="Browse Jenkins jobs"
          >
            <Search size={12} />
          </button>
        </div>
      </div>

      {/* Parameters Section */}
      {categoryConfig?.jobPath && (
        <div className="pt-3 border-t border-gray-700">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold text-gray-400">Job Parameters</span>
            <button
              type="button"
              onClick={fetchJobParameters}
              disabled={loadingParams}
              className="px-2 py-0.5 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded text-[10px] flex items-center gap-1"
              title="Refresh parameters from Jenkins"
            >
              <RefreshCw size={10} className={loadingParams ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>

          {loadingParams ? (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <RefreshCw size={12} className="animate-spin" />
              Loading parameters...
            </div>
          ) : categoryConfig?.parameterDefinitions?.length > 0 ? (
            <div className="space-y-2">
              {categoryConfig.parameterDefinitions.map((param) => (
                <ParameterField
                  key={param.name}
                  param={param}
                  value={categoryConfig?.parameters?.[param.name] || ''}
                  onChange={(value) => updateParameter(param.name, value)}
                />
              ))}
              <p className="text-[10px] text-gray-500 mt-1">
                Set parameter values for this environment. Leave empty to use defaults.
              </p>
            </div>
          ) : (
            <p className="text-[10px] text-gray-500">
              No parameters found. Click Refresh to load from Jenkins.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function ParameterField({ param, value, onChange }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center">
      <div className="flex items-center gap-1">
        <span className="text-[10px] font-medium text-gray-400">{param.name}</span>
        {param.type === 'choice' && (
          <span className="text-[8px] text-amber-500 px-1 py-0.5 bg-amber-900/30 rounded">choice</span>
        )}
      </div>
      <div className="md:col-span-2">
        {param.type === 'choice' && param.choices?.length > 0 ? (
          <select
            value={value || param.defaultValue || ''}
            onChange={(e) => onChange(e.target.value)}
            className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="">-- Select --</option>
            {param.choices.map((choice) => (
              <option key={choice} value={choice}>{choice}</option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={param.defaultValue || `Enter ${param.name}`}
            className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
        )}
      </div>
    </div>
  );
}
