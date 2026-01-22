/**
 * Pipeline Configuration Section
 *
 * Wizard step for configuring build and deploy pipelines for services.
 * Uses global CI Providers (providerId) instead of hardcoded provider types.
 */
import { useState, useCallback, useEffect } from 'react';
import { GitBranch, Layers, Server, RefreshCw, AlertCircle } from 'lucide-react';
import { fetchWithRetry } from '../../../utils/fetch';
import { PIPELINE_CATEGORY_LABELS } from './constants';
import { getProviderConfigComponent } from './providers';
import PipelineDiscoveryModal from './PipelineDiscoveryModal';

export default function PipelineConfigSection({
  services,
  pipelines,
  project,
  onPipelinesChange,
}) {
  // CI Providers from global config
  const [ciProviders, setCiProviders] = useState([]);
  const [providersLoading, setProvidersLoading] = useState(true);
  const [providersError, setProvidersError] = useState(null);

  // Discovery modal state
  const [discovery, setDiscovery] = useState({
    open: false,
    providerId: null,
    providerType: null,
    loading: false,
    error: null,
    currentPath: '/',
    items: [],
    filter: '',
    serviceId: null,
    category: null,
    fieldKey: null,
  });

  const showBuild = project?.pipelines?.buildMode === 'environment';
  const categories = showBuild ? ['build', 'deploy'] : ['deploy'];

  // Fetch CI Providers on mount
  useEffect(() => {
    fetchCIProviders();
  }, []);

  const fetchCIProviders = async () => {
    setProvidersLoading(true);
    setProvidersError(null);
    try {
      const response = await fetchWithRetry('/api/config/ci-providers');
      if (!response.ok) throw new Error('Failed to fetch CI providers');
      const data = await response.json();
      setCiProviders(data.ciProviders || []);
    } catch (err) {
      console.error('Error fetching CI providers:', err);
      setProvidersError(err.message);
    } finally {
      setProvidersLoading(false);
    }
  };

  // Get provider type from providerId
  const getProviderType = useCallback((providerId) => {
    const provider = ciProviders.find((p) => p.providerId === providerId);
    return provider?.type || 'jenkins';
  }, [ciProviders]);

  // Update pipeline config for a service/category
  const updateServiceConfig = useCallback((serviceId, category, updates) => {
    onPipelinesChange({
      ...pipelines,
      services: {
        ...pipelines.services,
        [serviceId]: {
          ...pipelines.services?.[serviceId],
          [category]: updates,
        },
      },
    });
  }, [pipelines, onPipelinesChange]);

  // Toggle pipeline enabled state
  const toggleEnabled = (serviceId, category, enabled) => {
    const serviceConfig = pipelines?.services?.[serviceId] || {};
    const categoryConfig = serviceConfig[category] || {};
    const defaultProviderId = ciProviders[0]?.providerId || '';

    updateServiceConfig(serviceId, category, {
      ...categoryConfig,
      enabled,
      providerId: enabled ? (categoryConfig.providerId || defaultProviderId) : categoryConfig.providerId,
    });
  };

  // Change provider
  const changeProvider = (serviceId, category, providerId) => {
    updateServiceConfig(serviceId, category, {
      enabled: true,
      providerId,
      // Reset job-specific config when provider changes
      jobPath: '',
      parameters: {},
      parameterDefinitions: [],
    });
  };

  // Open discovery modal
  const openDiscovery = async (providerId, serviceId, category, fieldKey) => {
    const providerType = getProviderType(providerId);

    setDiscovery({
      open: true,
      providerId,
      providerType,
      loading: true,
      error: null,
      currentPath: '/',
      items: [],
      filter: '',
      serviceId,
      category,
      fieldKey,
    });

    await discoverPipelines(providerId, providerType, '/');
  };

  // Discover pipelines
  const discoverPipelines = async (providerId, providerType, path = '/') => {
    setDiscovery(prev => ({ ...prev, loading: true, error: null }));

    try {
      let response;
      let data;

      if (providerType === 'jenkins') {
        const params = new URLSearchParams({
          providerId,
          path: path === '/' ? '' : path,
          includeParams: 'true',
        });
        response = await fetchWithRetry(`/api/pipelines/jenkins/discover?${params}`);
        data = await response.json();

        if (!response.ok) {
          throw new Error(data.message || data.error || 'Jenkins discovery failed');
        }

        const items = (data.items || []).map(item => ({
          name: item.name,
          path: item.fullPath || item.path,
          type: item.type === 'folder' ? 'folder' : 'job',
          parameters: item.parameters,
        }));

        setDiscovery(prev => ({
          ...prev,
          loading: false,
          currentPath: data.currentPath || path,
          items,
        }));
      } else {
        // ArgoCD and others use generic discovery
        response = await fetchWithRetry('/api/config/secrets/discover', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: providerType,
            path: path === '/' ? '' : path,
          }),
        });

        data = await response.json();

        if (!response.ok || !data.success) {
          throw new Error(data.message || data.error || 'Discovery failed');
        }

        setDiscovery(prev => ({
          ...prev,
          loading: false,
          currentPath: data.currentPath || path,
          items: data.items || [],
        }));
      }
    } catch (err) {
      console.error('Pipeline discovery error:', err);
      setDiscovery(prev => ({
        ...prev,
        loading: false,
        error: err.message,
      }));
    }
  };

  // Select item from discovery
  const selectDiscoveryItem = async (item) => {
    const { serviceId, category, fieldKey, providerId, providerType } = discovery;
    const value = item.path || item.name;

    // Update the config with selected value
    const serviceConfig = pipelines?.services?.[serviceId] || {};
    const categoryConfig = serviceConfig[category] || {};

    updateServiceConfig(serviceId, category, {
      ...categoryConfig,
      [fieldKey]: value,
    });

    // Close modal
    setDiscovery(prev => ({ ...prev, open: false }));

    // For Jenkins, also store parameters if available
    if (providerType === 'jenkins' && item.parameters?.length > 0) {
      updateServiceConfig(serviceId, category, {
        ...categoryConfig,
        [fieldKey]: value,
        parameterDefinitions: item.parameters,
        parameters: categoryConfig.parameters ||
          item.parameters.reduce((acc, param) => {
            acc[param.name] = param.defaultValue || '';
            return acc;
          }, {}),
      });
    }
  };

  // Close discovery modal
  const closeDiscovery = () => {
    setDiscovery(prev => ({ ...prev, open: false }));
  };

  // Handle discovery filter change
  const handleFilterChange = (filter) => {
    setDiscovery(prev => ({ ...prev, filter }));
  };

  // Navigate to folder
  const navigateToFolder = (path) => {
    discoverPipelines(discovery.providerId, discovery.providerType, path);
  };

  // Retry discovery
  const retryDiscovery = () => {
    discoverPipelines(discovery.providerId, discovery.providerType, discovery.currentPath);
  };

  if (providersLoading) {
    return (
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center justify-center py-8 text-gray-500">
            <RefreshCw size={20} className="animate-spin mr-2" />
            Loading CI providers...
          </div>
        </div>
      </div>
    );
  }

  if (providersError) {
    return (
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex flex-col items-center py-8 text-center">
            <AlertCircle size={32} className="text-red-400 mb-2" />
            <p className="text-red-400">{providersError}</p>
            <button
              onClick={fetchCIProviders}
              className="mt-4 px-3 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-white rounded"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (ciProviders.length === 0) {
    return (
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <GitBranch size={18} className="text-green-400" />
            Pipeline Configuration
          </h2>
          <div className="text-center py-8 text-gray-500">
            <Layers size={32} className="mx-auto mb-2 opacity-50" />
            <p>No CI providers configured.</p>
            <p className="text-xs mt-1">
              Add a CI provider in{' '}
              <a href="/admin/config/ci-providers" className="text-blue-400 hover:underline">
                Settings &gt; CI Providers
              </a>{' '}
              first.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (services.length === 0) {
    return (
      <div className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <GitBranch size={18} className="text-green-400" />
            Pipeline Configuration
          </h2>
          <div className="text-center py-8 text-gray-500">
            <Layers size={32} className="mx-auto mb-2 opacity-50" />
            <p>No services configured.</p>
            <p className="text-xs mt-1">Add services in the previous step to configure pipelines.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
          <GitBranch size={18} className="text-green-400" />
          Pipeline Configuration
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          Configure build and deploy pipelines for your services.
          {showBuild && (
            <span className="block mt-1 text-xs text-amber-400">
              Build pipelines are configured per environment for this project.
            </span>
          )}
        </p>

        <div className="space-y-4">
          {services.map((serviceId) => {
            const serviceConfig = pipelines?.services?.[serviceId] || {};

            return (
              <div
                key={serviceId}
                className="bg-gray-800/60 border border-gray-800 rounded-lg p-4"
              >
                <div className="flex items-center gap-2 mb-3">
                  <Server size={16} className="text-blue-400" />
                  <span className="font-medium text-white">{serviceId}</span>
                </div>

                <div className="space-y-3">
                  {categories.map((category) => (
                    <PipelineCategoryConfig
                      key={category}
                      serviceId={serviceId}
                      category={category}
                      serviceConfig={serviceConfig}
                      categoryConfig={serviceConfig[category] || {}}
                      ciProviders={ciProviders}
                      getProviderType={getProviderType}
                      onToggle={(enabled) => toggleEnabled(serviceId, category, enabled)}
                      onProviderChange={(providerId) => changeProvider(serviceId, category, providerId)}
                      onConfigChange={updateServiceConfig}
                      onOpenDiscovery={openDiscovery}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Discovery Modal */}
      <PipelineDiscoveryModal
        discovery={discovery}
        onClose={closeDiscovery}
        onFilterChange={handleFilterChange}
        onNavigate={navigateToFolder}
        onSelect={selectDiscoveryItem}
        onRetry={retryDiscovery}
      />
    </div>
  );
}

function PipelineCategoryConfig({
  serviceId,
  category,
  serviceConfig,
  categoryConfig,
  ciProviders,
  getProviderType,
  onToggle,
  onProviderChange,
  onConfigChange,
  onOpenDiscovery,
}) {
  const isEnabled = categoryConfig?.enabled || false;
  const providerId = categoryConfig?.providerId || ciProviders[0]?.providerId || '';
  const providerType = getProviderType(providerId);
  const ProviderConfig = getProviderConfigComponent(providerType);

  // Find the selected provider for display
  const selectedProvider = ciProviders.find((p) => p.providerId === providerId);

  return (
    <div
      className={`p-3 rounded-lg border ${isEnabled ? 'bg-gray-900/60 border-gray-700' : 'bg-gray-900/30 border-gray-800'}`}
    >
      <div className="flex items-center justify-between mb-2">
        <span className={`text-xs font-semibold ${isEnabled ? 'text-white' : 'text-gray-500'}`}>
          {PIPELINE_CATEGORY_LABELS[category]}
        </span>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <span className="text-[10px] text-gray-500">
            {isEnabled ? 'On' : 'Off'}
          </span>
          <input
            type="checkbox"
            checked={isEnabled}
            onChange={(e) => onToggle(e.target.checked)}
            className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
          />
        </label>
      </div>

      {isEnabled && (
        <div className="space-y-2">
          {/* Provider selector - now shows global CI Providers */}
          <div>
            <label className="block text-[10px] font-medium text-gray-500 mb-0.5">CI Provider</label>
            <select
              value={providerId}
              onChange={(e) => onProviderChange(e.target.value)}
              className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:border-blue-500 focus:outline-none"
            >
              {ciProviders.map((provider) => (
                <option key={provider.providerId} value={provider.providerId}>
                  {provider.name || provider.providerId} ({provider.type})
                </option>
              ))}
            </select>
            {selectedProvider?.url && (
              <p className="text-[9px] text-gray-600 mt-0.5 truncate">{selectedProvider.url}</p>
            )}
          </div>

          {/* Provider-specific config */}
          {ProviderConfig && (
            <ProviderConfig
              serviceId={serviceId}
              category={category}
              categoryConfig={categoryConfig}
              serviceConfig={serviceConfig}
              providerId={providerId}
              onConfigChange={onConfigChange}
              onOpenDiscovery={(fieldKey) => onOpenDiscovery(providerId, serviceId, category, fieldKey)}
            />
          )}
        </div>
      )}
    </div>
  );
}
