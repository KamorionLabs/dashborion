/**
 * ProjectForm - Create/Edit Project
 *
 * Form to configure project settings.
 */
import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  FolderKanban,
  Save,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  Layers,
  Plus,
  Trash2,
  Compass,
  GitBranch,
  Search,
  Folder,
  FolderOpen,
  ChevronRight,
  X,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const AWS_REGIONS = [
  { value: 'eu-central-1', label: 'EU (Frankfurt)' },
  { value: 'eu-west-1', label: 'EU (Ireland)' },
  { value: 'eu-west-2', label: 'EU (London)' },
  { value: 'eu-west-3', label: 'EU (Paris)' },
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'us-west-2', label: 'US West (Oregon)' },
];

const TOPOLOGY_PRESETS = {
  ecs: ['edge', 'ingress', 'frontend', 'application', 'data'],
  eks: ['edge', 'ingress', 'frontend', 'proxy', 'application', 'search', 'data'],
};

const PIPELINE_PROVIDER_TYPES = [
  { value: 'codepipeline', label: 'AWS CodePipeline' },
  { value: 'jenkins', label: 'Jenkins' },
  { value: 'argocd', label: 'ArgoCD' },
  { value: 'github-actions', label: 'GitHub Actions' },
  { value: 'azure-devops', label: 'Azure DevOps' },
];

// Provider-specific field definitions
const PIPELINE_PROVIDER_FIELDS = {
  codepipeline: [
    { key: 'accountId', label: 'AWS Account', type: 'aws-account' },
    { key: 'region', label: 'Region', type: 'aws-region' },
  ],
  jenkins: [
    { key: 'jobPath', label: 'Job Path', type: 'text', placeholder: 'RubixDeployment/EKS/STAGING/deploy-service' },
  ],
  argocd: [
    { key: 'appName', label: 'Application Name', type: 'text', placeholder: 'my-app-staging' },
    { key: 'project', label: 'ArgoCD Project', type: 'text', placeholder: 'default' },
  ],
  'github-actions': [
    { key: 'repo', label: 'Repository', type: 'text', placeholder: 'org/repo' },
    { key: 'workflow', label: 'Workflow', type: 'text', placeholder: 'deploy.yml' },
  ],
  'azure-devops': [
    { key: 'organization', label: 'Organization', type: 'text', placeholder: 'my-org' },
    { key: 'adoProject', label: 'Project', type: 'text', placeholder: 'MyProject' },
    { key: 'pipelineId', label: 'Pipeline ID', type: 'text', placeholder: '123' },
  ],
};

// Categories for pipeline configuration
const PIPELINE_CATEGORIES = ['build', 'deploy'];
const PIPELINE_CATEGORY_LABELS = {
  build: 'Build (CI)',
  deploy: 'Deploy (CD)',
};

export default function ProjectForm() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(projectId);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const [form, setForm] = useState({
    projectId: '',
    displayName: '',
    description: '',
    orchestratorType: '',  // eks, ecs, or empty
    serviceNaming: { prefix: '' },
    topology: null,
    pipelines: { enabled: false, services: {} },
  });

  const [newLayer, setNewLayer] = useState('');
  const [newComponent, setNewComponent] = useState({
    id: '',
    label: '',
    type: 'service',
    layer: '',
    group: '',
  });
  const [newConnection, setNewConnection] = useState({
    from: '',
    to: '',
    protocol: '',
  });

  const [awsAccounts, setAwsAccounts] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [discoveryState, setDiscoveryState] = useState({
    accountId: '',
    region: '',
    cluster: '',
    namespace: '',
    layer: 'application',
    resources: [],
    selected: [],
  });
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [discoveryError, setDiscoveryError] = useState(null);
  const [namespaceOptions, setNamespaceOptions] = useState([]);

  // Pipeline discovery state
  const [pipelineDiscovery, setPipelineDiscovery] = useState({
    open: false,
    provider: null,
    loading: false,
    error: null,
    currentPath: '/',
    items: [],
    filter: '',
    // Callback info for selection
    serviceId: null,
    category: null,
    fieldKey: null,
  });

  const discoveryOrchestratorReady = form.orchestratorType === 'ecs' || form.orchestratorType === 'eks';

  // Load existing project for edit
  useEffect(() => {
    if (isEdit) {
      loadProject();
    }
  }, [projectId]);

  useEffect(() => {
    loadDiscoveryResources();
  }, []);

  useEffect(() => {
    if (!discoveryState.accountId) return;
    const account = awsAccounts.find((item) => item.accountId === discoveryState.accountId);
    if (account?.defaultRegion && !discoveryState.region) {
      setDiscoveryState((prev) => ({ ...prev, region: account.defaultRegion }));
    }
  }, [awsAccounts, discoveryState.accountId, discoveryState.region]);

  useEffect(() => {
    setDiscoveryState((prev) => ({
      ...prev,
      resources: [],
      selected: [],
      namespace: form.orchestratorType === 'eks' ? prev.namespace : '',
    }));
  }, [form.orchestratorType]);

  const loadDiscoveryResources = async () => {
    try {
      const [accountsRes, clustersRes] = await Promise.all([
        fetchWithRetry('/api/config/aws-accounts'),
        fetchWithRetry('/api/config/clusters'),
      ]);

      if (accountsRes.ok) {
        const data = await accountsRes.json();
        setAwsAccounts(data.awsAccounts || []);
      }
      if (clustersRes.ok) {
        const data = await clustersRes.json();
        setClusters(data.clusters || []);
      }
    } catch (err) {
      console.error('Error loading discovery resources:', err);
    }
  };

  const loadProject = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(`/api/config/projects/${projectId}`);

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Project not found');
        }
        throw new Error('Failed to load project');
      }

      const data = await response.json();
      setForm({
        projectId: data.projectId || '',
        displayName: data.displayName || '',
        description: data.description || '',
        orchestratorType: data.orchestratorType || '',
        serviceNaming: data.serviceNaming || { prefix: '' },
        topology: data.topology || null,
        pipelines: data.pipelines || { enabled: false, services: {} },
      });
    } catch (err) {
      console.error('Error loading project:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.projectId) {
      setError('Project ID is required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const method = isEdit ? 'PUT' : 'POST';
      const url = isEdit
        ? `/api/config/projects/${projectId}`
        : '/api/config/projects';

      const normalizedTopology = normalizeTopology(form.topology);
      const payload = {
        projectId: form.projectId,
        displayName: form.displayName,
        description: form.description,
        orchestratorType: form.orchestratorType,
        serviceNaming: form.serviceNaming || {},
        pipelines: form.pipelines || { enabled: false, providers: [] },
      };
      if (normalizedTopology) {
        payload.topology = normalizedTopology;
      }

      const response = await fetchWithRetry(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save project');
      }

      navigate('/admin/config/projects');
    } catch (err) {
      console.error('Error saving project:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Pipeline discovery functions
  const openPipelineDiscovery = async (provider, serviceId, category, fieldKey) => {
    setPipelineDiscovery({
      open: true,
      provider,
      loading: true,
      error: null,
      currentPath: '/',
      items: [],
      filter: '',
      serviceId,
      category,
      fieldKey,
    });

    await discoverPipelines(provider, '/');
  };

  const discoverPipelines = async (provider, path = '/') => {
    setPipelineDiscovery(prev => ({ ...prev, loading: true, error: null }));

    try {
      const response = await fetchWithRetry('/api/config/secrets/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: provider.replace('-token', ''),
          path: path === '/' ? '' : path,
        }),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || 'Discovery failed');
      }

      setPipelineDiscovery(prev => ({
        ...prev,
        loading: false,
        currentPath: data.currentPath || path,
        items: data.items || [],
      }));
    } catch (err) {
      console.error('Pipeline discovery error:', err);
      setPipelineDiscovery(prev => ({
        ...prev,
        loading: false,
        error: err.message,
      }));
    }
  };

  const navigateToFolder = (path) => {
    discoverPipelines(pipelineDiscovery.provider, path);
  };

  const selectPipelineItem = (item) => {
    const { serviceId, category, fieldKey } = pipelineDiscovery;

    // Update the form with selected value
    setForm(prev => ({
      ...prev,
      pipelines: {
        ...prev.pipelines,
        services: {
          ...prev.pipelines.services,
          [serviceId]: {
            ...prev.pipelines.services[serviceId],
            [category]: {
              ...prev.pipelines.services[serviceId]?.[category],
              [fieldKey]: item.path || item.name,
            },
          },
        },
      },
    }));

    // Close modal
    setPipelineDiscovery(prev => ({ ...prev, open: false }));
  };

  const closePipelineDiscovery = () => {
    setPipelineDiscovery(prev => ({ ...prev, open: false }));
  };

  const normalizeTopology = (topology) => {
    if (!topology) return null;
    const layers = Array.isArray(topology.layers) ? topology.layers.filter(Boolean) : [];
    const components = topology.components && typeof topology.components === 'object' ? topology.components : {};
    const connections = Array.isArray(topology.connections) ? topology.connections : [];

    const normalizedComponents = Object.fromEntries(
      Object.entries(components)
        .map(([id, component]) => [
          id.trim(),
          {
            type: component?.type || 'service',
            layer: component?.layer || '',
            label: component?.label || '',
            group: component?.group || '',
          },
        ])
        .filter(([id]) => id)
    );

    const normalizedConnections = connections
      .map((conn) => ({
        from: (conn?.from || '').trim(),
        to: (conn?.to || '').trim(),
        protocol: (conn?.protocol || '').trim(),
      }))
      .filter((conn) => conn.from && conn.to);

    if (!layers.length && !Object.keys(normalizedComponents).length && !normalizedConnections.length) {
      return null;
    }

    return {
      ...(layers.length ? { layers } : {}),
      ...(Object.keys(normalizedComponents).length ? { components: normalizedComponents } : {}),
      ...(normalizedConnections.length ? { connections: normalizedConnections } : {}),
    };
  };

  const normalizeTopologyShape = (topology) => ({
    layers: Array.isArray(topology?.layers) ? topology.layers : [],
    components: topology?.components && typeof topology.components === 'object' ? topology.components : {},
    connections: Array.isArray(topology?.connections) ? topology.connections : [],
  });

  const updateTopology = (updater) => {
    setForm((prev) => {
      const current = normalizeTopologyShape(prev.topology);
      const next = updater(current);
      return { ...prev, topology: next };
    });
  };

  const addLayer = () => {
    const value = newLayer.trim();
    if (!value) return;
    updateTopology((topology) => {
      if (topology.layers.includes(value)) return topology;
      return { ...topology, layers: [...topology.layers, value] };
    });
    setNewLayer('');
  };

  const removeLayer = (value) => {
    updateTopology((topology) => ({
      ...topology,
      layers: topology.layers.filter((layer) => layer !== value),
    }));
  };

  const addComponent = () => {
    const id = newComponent.id.trim();
    if (!id) return;
    updateTopology((topology) => ({
      ...topology,
      components: {
        ...topology.components,
        [id]: {
          type: newComponent.type || 'service',
          layer: newComponent.layer || '',
          label: newComponent.label || '',
          group: newComponent.group || '',
        },
      },
    }));
    setNewComponent({ id: '', label: '', type: 'service', layer: '', group: '' });
  };

  const updateComponent = (id, field, value) => {
    updateTopology((topology) => ({
      ...topology,
      components: {
        ...topology.components,
        [id]: {
          ...topology.components[id],
          [field]: value,
        },
      },
    }));
  };

  const removeComponent = (id) => {
    updateTopology((topology) => {
      const { [id]: _, ...rest } = topology.components;
      const connections = topology.connections.filter((conn) => conn.from !== id && conn.to !== id);
      return { ...topology, components: rest, connections };
    });
  };

  const addConnection = () => {
    const from = newConnection.from.trim();
    const to = newConnection.to.trim();
    if (!from || !to) return;
    updateTopology((topology) => ({
      ...topology,
      connections: [
        ...topology.connections,
        { from, to, protocol: newConnection.protocol.trim() },
      ],
    }));
    setNewConnection({ from: '', to: '', protocol: '' });
  };

  const updateConnection = (index, field, value) => {
    updateTopology((topology) => {
      const next = [...topology.connections];
      next[index] = { ...next[index], [field]: value };
      return { ...topology, connections: next };
    });
  };

  const removeConnection = (index) => {
    updateTopology((topology) => ({
      ...topology,
      connections: topology.connections.filter((_, idx) => idx !== index),
    }));
  };

  const applyLayerPreset = (preset) => {
    const layers = TOPOLOGY_PRESETS[preset] || [];
    if (layers.length === 0) return;
    updateTopology((topology) => {
      const merged = [...topology.layers];
      layers.forEach((layer) => {
        if (!merged.includes(layer)) {
          merged.push(layer);
        }
      });
      return { ...topology, layers: merged };
    });
  };

  const clusterOptions = useMemo(() => {
    const accountId = discoveryState.accountId;
    const region = discoveryState.region;
    const orchestratorType = form.orchestratorType;

    return clusters.filter((cluster) => {
      const clusterAccount = cluster.awsAccountId || cluster.accountId || '';
      const clusterRegion = cluster.region || '';
      const clusterType = cluster.type || null;

      if (accountId && clusterAccount && clusterAccount !== accountId) return false;
      if (region && clusterRegion && clusterRegion !== region) return false;
      if (orchestratorType && clusterType && clusterType !== orchestratorType) return false;
      return true;
    });
  }, [clusters, discoveryState.accountId, discoveryState.region, form.orchestratorType]);

  const getClusterId = (cluster) => cluster.clusterId || cluster.id || cluster.name || '';
  const getClusterName = (cluster) => cluster.clusterName || cluster.name || cluster.clusterId || cluster.id || '';

  const clusterSelectOptions = useMemo(() => {
    return clusterOptions.length > 0 ? clusterOptions : clusters;
  }, [clusterOptions, clusters]);

  const selectedCluster = useMemo(() => {
    return clusterSelectOptions.find((cluster) => {
      const clusterName = getClusterName(cluster);
      const clusterId = getClusterId(cluster);
      return clusterName === discoveryState.cluster || clusterId === discoveryState.cluster;
    }) || null;
  }, [clusterSelectOptions, discoveryState.cluster]);

  const discoveryClusterValue = selectedCluster ? getClusterId(selectedCluster) : '';

  const discoverNamespaces = async () => {
    if (!discoveryOrchestratorReady) {
      setDiscoveryError('Select an orchestrator type before discovery.');
      return;
    }
    if (!discoveryState.accountId || !discoveryState.cluster) return;
    setDiscoveryError(null);
    setDiscoveryLoading(true);
    try {
      const clusterName = selectedCluster ? getClusterName(selectedCluster) : discoveryState.cluster;
      const params = new URLSearchParams();
      if (discoveryState.region) params.set('region', discoveryState.region);
      params.set('cluster', clusterName);
      const res = await fetchWithRetry(
        `/api/config/discovery/${discoveryState.accountId}/eks-namespaces?${params.toString()}`
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || 'Failed to discover namespaces');
      }
      const resources = data.resources || [];
      if (resources[0]?.error) {
        throw new Error(resources[0].error);
      }
      setNamespaceOptions(resources.map((ns) => ns.name));
    } catch (err) {
      setDiscoveryError(err.message);
    } finally {
      setDiscoveryLoading(false);
    }
  };

  const discoverServices = async () => {
    if (!discoveryOrchestratorReady) {
      setDiscoveryError('Select an orchestrator type before discovery.');
      return;
    }
    if (!discoveryState.accountId || !discoveryState.cluster) return;
    if (form.orchestratorType === 'eks' && !discoveryState.namespace) return;
    setDiscoveryError(null);
    setDiscoveryLoading(true);
    try {
      const clusterName = selectedCluster ? getClusterName(selectedCluster) : discoveryState.cluster;
      const params = new URLSearchParams();
      if (discoveryState.region) params.set('region', discoveryState.region);
      params.set('cluster', clusterName);
      if (form.orchestratorType === 'eks') {
        params.set('namespace', discoveryState.namespace);
      }
      const resourceType = form.orchestratorType === 'ecs' ? 'ecs-services' : 'eks-workloads';
      const res = await fetchWithRetry(
        `/api/config/discovery/${discoveryState.accountId}/${resourceType}?${params.toString()}`
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || 'Failed to discover services');
      }
      const resources = data.resources || [];
      if (resources[0]?.error) {
        throw new Error(resources[0].error);
      }
      setDiscoveryState((prev) => ({
        ...prev,
        resources,
        selected: resources.map((item) => item.id || item.name),
      }));
    } catch (err) {
      setDiscoveryError(err.message);
    } finally {
      setDiscoveryLoading(false);
    }
  };

  const toggleDiscoverySelection = (id) => {
    setDiscoveryState((prev) => {
      const selected = prev.selected.includes(id)
        ? prev.selected.filter((item) => item !== id)
        : [...prev.selected, id];
      return { ...prev, selected };
    });
  };

  const addDiscoveredComponents = () => {
    const resources = discoveryState.resources || [];
    if (!resources.length) return;
    updateTopology((topology) => {
      const nextComponents = { ...topology.components };
      const nextLayers = [...topology.layers];
      resources.forEach((item) => {
        const id = item.id || item.name;
        if (!id || !discoveryState.selected.includes(id)) return;
        const type = item.type
          || (form.orchestratorType === 'ecs' ? 'ecs-service' : 'k8s-deployment');
        const layer = discoveryState.layer || 'application';
        if (layer && !nextLayers.includes(layer)) {
          nextLayers.push(layer);
        }
        nextComponents[id] = {
          type,
          layer,
          label: item.name || id,
          group: '',
        };
      });
      return { ...topology, layers: nextLayers, components: nextComponents };
    });
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-64">
          <RefreshCw size={24} className="animate-spin text-gray-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl">
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/admin/config/projects"
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft size={16} />
          Back to Projects
        </Link>
        <h1 className="text-2xl font-semibold text-white">
          {isEdit ? 'Edit Project' : 'Create Project'}
        </h1>
        <p className="text-gray-500">
          Configure project settings and metadata
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg flex items-center gap-3">
          <AlertCircle size={20} className="text-red-400" />
          <span className="text-red-400">{error}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Project ID */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Project ID <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={form.projectId}
            onChange={(e) => setForm({ ...form, projectId: e.target.value })}
            disabled={isEdit}
            placeholder="my-project"
            pattern="[a-z0-9-]+"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
          />
          <p className="mt-1 text-xs text-gray-500">
            Lowercase letters, numbers, and hyphens only (e.g., mro-mi2, webshop-de)
          </p>
        </div>

        {/* Display Name */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Display Name
          </label>
          <input
            type="text"
            value={form.displayName}
            onChange={(e) => setForm({ ...form, displayName: e.target.value })}
            placeholder="My Project"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Description
          </label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Brief description of the project..."
            rows={3}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none resize-none"
          />
        </div>

        {/* Orchestrator Type */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Orchestrator Type
          </label>
          <select
            value={form.orchestratorType}
            onChange={(e) => setForm({ ...form, orchestratorType: e.target.value })}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="">None / Not specified</option>
            <option value="eks">EKS (Kubernetes)</option>
            <option value="ecs">ECS (Fargate/EC2)</option>
          </select>
          <p className="mt-1 text-xs text-gray-500">
            Container orchestrator used by all environments in this project
          </p>
        </div>

        {/* Service Naming */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Service Prefix
          </label>
          <input
            type="text"
            value={form.serviceNaming?.prefix || ''}
            onChange={(e) => setForm({
              ...form,
              serviceNaming: { ...(form.serviceNaming || {}), prefix: e.target.value },
            })}
            placeholder="{project}-{env}-"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
          <p className="mt-1 text-xs text-gray-500">
            Prefix template for service names. Supports {`{project}`} and {`{env}`}.
          </p>
        </div>

        {/* Topology */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 space-y-5">
          <div className="flex items-center gap-2">
            <Layers size={18} className="text-blue-400" />
            <div>
              <h2 className="text-lg font-semibold text-white">Topology</h2>
              <p className="text-xs text-gray-500">
                Define layers, components, and connections for the infrastructure diagram.
              </p>
            </div>
          </div>

          {(() => {
            const topology = normalizeTopologyShape(form.topology);
            const componentEntries = Object.entries(topology.components || {});
            const layerOptions = topology.layers || [];
            const connectionOptions = componentEntries.map(([id]) => id);

            return (
              <div className="space-y-6">
                <div className="border border-gray-800 rounded-lg p-4 bg-gray-900/60">
                  <div className="flex items-center gap-2 mb-3">
                    <Compass size={16} className="text-blue-400" />
                    <div>
                      <div className="text-sm font-semibold text-white">Quick setup</div>
                      <div className="text-xs text-gray-500">
                        Use presets and discovery to build the base topology quickly.
                      </div>
                    </div>
                  </div>
                  {!discoveryOrchestratorReady && (
                    <div className="mb-3 text-xs text-amber-400">
                      Select an orchestrator type to enable ECS/EKS discovery.
                    </div>
                  )}

                  <div className="flex flex-wrap gap-2 mb-4">
                    <button
                      type="button"
                      onClick={() => applyLayerPreset('ecs')}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Add ECS layer preset
                    </button>
                    <button
                      type="button"
                      onClick={() => applyLayerPreset('eks')}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Add EKS layer preset
                    </button>
                    <span className="text-xs text-gray-500 self-center">
                      Presets add missing layers without overwriting existing ones.
                    </span>
                  </div>

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">
                        AWS Account
                      </label>
                      <select
                        value={discoveryState.accountId}
                        onChange={(e) => setDiscoveryState((prev) => ({
                          ...prev,
                          accountId: e.target.value,
                          cluster: '',
                          namespace: '',
                          resources: [],
                          selected: [],
                        }))}
                        className="w-full px-2.5 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none"
                      >
                        <option value="">Select account</option>
                        {awsAccounts.map((account) => (
                          <option key={account.accountId} value={account.accountId}>
                            {account.displayName || account.accountId}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">
                        Region
                      </label>
                      <select
                        value={discoveryState.region}
                        onChange={(e) => setDiscoveryState((prev) => ({ ...prev, region: e.target.value }))}
                        className="w-full px-2.5 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none"
                      >
                        <option value="">Use account default</option>
                        {AWS_REGIONS.map((region) => (
                          <option key={region.value} value={region.value}>
                            {region.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">
                        Cluster
                      </label>
                      <select
                        value={discoveryClusterValue}
                        onChange={(e) => {
                          const clusterId = e.target.value;
                          const clusterMatch = clusterSelectOptions.find(
                            (cluster) => getClusterId(cluster) === clusterId
                          );
                          setDiscoveryState((prev) => ({
                            ...prev,
                            cluster: clusterId,
                            region: clusterMatch?.region || prev.region,
                            resources: [],
                            selected: [],
                          }));
                        }}
                        className="w-full px-2.5 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-blue-500 focus:outline-none"
                      >
                        <option value="">Select cluster</option>
                        {clusterSelectOptions.map((cluster) => (
                          <option key={getClusterId(cluster)} value={getClusterId(cluster)}>
                            {getClusterName(cluster)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {form.orchestratorType === 'eks' && (
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-3">
                      <div className="lg:col-span-2">
                        <label className="block text-xs font-medium text-gray-400 mb-1">
                          Namespace
                        </label>
                        <input
                          type="text"
                          value={discoveryState.namespace}
                          onChange={(e) => setDiscoveryState((prev) => ({
                            ...prev,
                            namespace: e.target.value,
                            resources: [],
                            selected: [],
                          }))}
                          placeholder="Namespace to scan"
                          list="discovered-namespaces"
                          className="w-full px-2.5 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                        />
                        <datalist id="discovered-namespaces">
                          {namespaceOptions.map((ns) => (
                            <option key={ns} value={ns} />
                          ))}
                        </datalist>
                      </div>
                      <div className="flex items-end">
                      <button
                        type="button"
                        onClick={discoverNamespaces}
                        disabled={
                          !discoveryOrchestratorReady
                          || !discoveryState.accountId
                          || !discoveryState.cluster
                          || discoveryLoading
                        }
                        className="w-full px-3 py-2 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                      >
                        Discover namespaces
                      </button>
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-3">
                    <div>
                      <label className="block text-xs font-medium text-gray-400 mb-1">
                        Default layer for imports
                      </label>
                      <input
                        type="text"
                        value={discoveryState.layer}
                        onChange={(e) => setDiscoveryState((prev) => ({ ...prev, layer: e.target.value }))}
                        list="topology-layers"
                        placeholder="application"
                        className="w-full px-2.5 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={discoverServices}
                        disabled={
                          !discoveryOrchestratorReady
                          || !form.orchestratorType
                          || !discoveryState.accountId
                          || !discoveryState.cluster
                          || (form.orchestratorType === 'eks' && !discoveryState.namespace)
                          || discoveryLoading
                        }
                        className="w-full px-3 py-2 text-xs rounded-md bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
                      >
                        Discover services
                      </button>
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={addDiscoveredComponents}
                        disabled={discoveryState.selected.length === 0}
                        className="w-full px-3 py-2 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                      >
                        Add selected components
                      </button>
                    </div>
                  </div>

                  {discoveryError && (
                    <div className="mt-3 text-xs text-red-400">{discoveryError}</div>
                  )}

                  {discoveryState.resources.length > 0 && (
                    <div className="mt-3 space-y-2 max-h-48 overflow-auto">
                      {discoveryState.resources.map((item) => {
                        const id = item.id || item.name;
                        const checked = discoveryState.selected.includes(id);
                        return (
                          <label
                            key={id}
                            className="flex items-center gap-2 text-xs text-gray-300 bg-gray-800/60 border border-gray-800 rounded-md px-2 py-1"
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => toggleDiscoverySelection(id)}
                            />
                            <span className="flex-1">{item.name || id}</span>
                            {item.type && (
                              <span className="text-gray-500">{item.type}</span>
                            )}
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Layers
                  </label>
                  <div className="flex gap-2 mb-3">
                    <input
                      type="text"
                      value={newLayer}
                      onChange={(e) => setNewLayer(e.target.value)}
                      placeholder="frontend"
                      className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                      onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addLayer())}
                    />
                    <button
                      type="button"
                      onClick={addLayer}
                      className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                    >
                      <Plus size={16} />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {layerOptions.map((layer) => (
                      <span
                        key={layer}
                        className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-sm text-gray-300"
                      >
                        {layer}
                        <button
                          type="button"
                          onClick={() => removeLayer(layer)}
                          className="text-gray-500 hover:text-red-400"
                        >
                          <Trash2 size={12} />
                        </button>
                      </span>
                    ))}
                    {layerOptions.length === 0 && (
                      <span className="text-xs text-gray-500">No layers defined yet.</span>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Components
                  </label>
                  <p className="text-xs text-gray-500 mb-2">
                    Component IDs should match ECS/EKS service names (short name, without project prefix).
                  </p>
                  <datalist id="topology-layers">
                    {layerOptions.map((layer) => (
                      <option key={layer} value={layer} />
                    ))}
                  </datalist>
                  <datalist id="topology-types">
                    <option value="ecs-service" />
                    <option value="k8s-deployment" />
                    <option value="k8s-statefulset" />
                    <option value="cdn" />
                    <option value="loadbalancer" />
                    <option value="rds" />
                    <option value="elasticache" />
                    <option value="efs" />
                    <option value="service" />
                  </datalist>
                  <div className="grid grid-cols-1 lg:grid-cols-5 gap-2 mb-3">
                    <input
                      type="text"
                      value={newComponent.id}
                      onChange={(e) => setNewComponent((prev) => ({ ...prev, id: e.target.value }))}
                      placeholder="service-id"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      value={newComponent.label}
                      onChange={(e) => setNewComponent((prev) => ({ ...prev, label: e.target.value }))}
                      placeholder="Label"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      value={newComponent.type}
                      onChange={(e) => setNewComponent((prev) => ({ ...prev, type: e.target.value }))}
                      placeholder="Type (ecs-service, k8s-deployment)"
                      list="topology-types"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      value={newComponent.layer}
                      onChange={(e) => setNewComponent((prev) => ({ ...prev, layer: e.target.value }))}
                      placeholder="Layer"
                      list="topology-layers"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={newComponent.group}
                        onChange={(e) => setNewComponent((prev) => ({ ...prev, group: e.target.value }))}
                        placeholder="Group"
                        className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={addComponent}
                        className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                      >
                        <Plus size={16} />
                      </button>
                    </div>
                  </div>

                  {componentEntries.length === 0 ? (
                    <p className="text-xs text-gray-500">No components defined yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {componentEntries.map(([id, component]) => (
                        <div
                          key={id}
                          className="grid grid-cols-1 lg:grid-cols-6 gap-2 items-center bg-gray-800/40 border border-gray-800 rounded-lg p-2"
                        >
                          <input
                            type="text"
                            value={id}
                            disabled
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-400"
                          />
                          <input
                            type="text"
                            value={component.label || ''}
                            onChange={(e) => updateComponent(id, 'label', e.target.value)}
                            placeholder="Label"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            value={component.type || ''}
                            onChange={(e) => updateComponent(id, 'type', e.target.value)}
                            placeholder="Type"
                            list="topology-types"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            value={component.layer || ''}
                            onChange={(e) => updateComponent(id, 'layer', e.target.value)}
                            placeholder="Layer"
                            list="topology-layers"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            value={component.group || ''}
                            onChange={(e) => updateComponent(id, 'group', e.target.value)}
                            placeholder="Group"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => removeComponent(id)}
                            className="px-2 py-1 text-sm text-red-400 hover:text-red-300"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Connections
                  </label>
                  <datalist id="topology-components">
                    {connectionOptions.map((option) => (
                      <option key={option} value={option} />
                    ))}
                  </datalist>
                  <div className="grid grid-cols-1 lg:grid-cols-4 gap-2 mb-3">
                    <input
                      type="text"
                      value={newConnection.from}
                      onChange={(e) => setNewConnection((prev) => ({ ...prev, from: e.target.value }))}
                      placeholder="from"
                      list="topology-components"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      value={newConnection.to}
                      onChange={(e) => setNewConnection((prev) => ({ ...prev, to: e.target.value }))}
                      placeholder="to"
                      list="topology-components"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <input
                      type="text"
                      value={newConnection.protocol}
                      onChange={(e) => setNewConnection((prev) => ({ ...prev, protocol: e.target.value }))}
                      placeholder="protocol"
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={addConnection}
                      className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                    >
                      <Plus size={16} />
                    </button>
                  </div>

                  {topology.connections.length === 0 ? (
                    <p className="text-xs text-gray-500">No connections defined yet.</p>
                  ) : (
                    <div className="space-y-2">
                      {topology.connections.map((conn, idx) => (
                        <div
                          key={`${conn.from}-${conn.to}-${idx}`}
                          className="grid grid-cols-1 lg:grid-cols-5 gap-2 items-center bg-gray-800/40 border border-gray-800 rounded-lg p-2"
                        >
                          <input
                            type="text"
                            value={conn.from}
                            onChange={(e) => updateConnection(idx, 'from', e.target.value)}
                            list="topology-components"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            value={conn.to}
                            onChange={(e) => updateConnection(idx, 'to', e.target.value)}
                            list="topology-components"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            value={conn.protocol || ''}
                            onChange={(e) => updateConnection(idx, 'protocol', e.target.value)}
                            placeholder="protocol"
                            className="px-2 py-1 bg-gray-900 border border-gray-800 rounded text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
                          />
                          <span className="text-xs text-gray-500"> </span>
                          <button
                            type="button"
                            onClick={() => removeConnection(idx)}
                            className="px-2 py-1 text-sm text-red-400 hover:text-red-300"
                          >
                            Remove
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>

        {/* Pipelines */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <GitBranch size={18} className="text-green-400" />
              <div>
                <h2 className="text-lg font-semibold text-white">Pipelines</h2>
                <p className="text-xs text-gray-500">
                  Configure build pipelines. Deploy pipelines are configured per environment.
                </p>
              </div>
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <span className="text-sm text-gray-400">Enable pipelines</span>
              <input
                type="checkbox"
                checked={form.pipelines?.enabled || false}
                onChange={(e) => setForm((prev) => ({
                  ...prev,
                  pipelines: { ...prev.pipelines, enabled: e.target.checked },
                }))}
                className="w-5 h-5 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
              />
            </label>
          </div>

          {form.pipelines?.enabled && (
            <div className="flex items-center gap-4 p-3 bg-gray-800/50 rounded-lg">
              <span className="text-sm text-gray-400">Build mode:</span>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="buildMode"
                  value="project"
                  checked={(form.pipelines?.buildMode || 'project') === 'project'}
                  onChange={() => setForm((prev) => ({
                    ...prev,
                    pipelines: { ...prev.pipelines, buildMode: 'project' },
                  }))}
                  className="w-4 h-4 border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-white">Per project</span>
                <span className="text-xs text-gray-500">(one build for all envs)</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="buildMode"
                  value="environment"
                  checked={form.pipelines?.buildMode === 'environment'}
                  onChange={() => setForm((prev) => ({
                    ...prev,
                    pipelines: { ...prev.pipelines, buildMode: 'environment' },
                  }))}
                  className="w-4 h-4 border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-white">Per environment</span>
                <span className="text-xs text-gray-500">(build configured per env)</span>
              </label>
            </div>
          )}

          {form.pipelines?.enabled && (form.pipelines?.buildMode || 'project') === 'project' && (() => {
            const pipelineServices = form.pipelines?.services || {};
            const serviceEntries = Object.entries(pipelineServices);
            const topologyComponents = Object.keys(normalizeTopologyShape(form.topology).components || {});

            // Get workload-type components from topology (services that can have pipelines)
            const workloadTypes = ['ecs-service', 'k8s-deployment', 'k8s-statefulset', 'service'];
            const workloadComponents = Object.entries(normalizeTopologyShape(form.topology).components || {})
              .filter(([_, comp]) => workloadTypes.includes(comp.type))
              .map(([id]) => id);
            const missingServices = workloadComponents.filter((id) => !pipelineServices[id]);

            // Helper to render provider-specific fields for a category
            const renderProviderFields = (serviceId, category, categoryConfig) => {
              const providerFields = PIPELINE_PROVIDER_FIELDS[categoryConfig?.provider] || [];
              if (providerFields.length === 0) return null;

              return (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                  {providerFields.map((field) => (
                    <div key={field.key}>
                      <label className="block text-[10px] font-medium text-gray-500 mb-0.5">{field.label}</label>
                      {field.type === 'aws-account' ? (
                        <select
                          value={categoryConfig?.[field.key] || ''}
                          onChange={(e) => setForm((prev) => ({
                            ...prev,
                            pipelines: {
                              ...prev.pipelines,
                              services: {
                                ...prev.pipelines.services,
                                [serviceId]: {
                                  ...prev.pipelines.services[serviceId],
                                  [category]: { ...categoryConfig, [field.key]: e.target.value },
                                },
                              },
                            },
                          }))}
                          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:border-blue-500 focus:outline-none"
                        >
                          <option value="">Select account</option>
                          {awsAccounts.map((account) => (
                            <option key={account.accountId} value={account.accountId}>
                              {account.displayName || account.accountId}
                            </option>
                          ))}
                        </select>
                      ) : field.type === 'aws-region' ? (
                        <select
                          value={categoryConfig?.[field.key] || ''}
                          onChange={(e) => setForm((prev) => ({
                            ...prev,
                            pipelines: {
                              ...prev.pipelines,
                              services: {
                                ...prev.pipelines.services,
                                [serviceId]: {
                                  ...prev.pipelines.services[serviceId],
                                  [category]: { ...categoryConfig, [field.key]: e.target.value },
                                },
                              },
                            },
                          }))}
                          className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:border-blue-500 focus:outline-none"
                        >
                          <option value="">Default region</option>
                          {AWS_REGIONS.map((region) => (
                            <option key={region.value} value={region.value}>{region.label}</option>
                          ))}
                        </select>
                      ) : (
                        <div className="flex gap-1">
                          <input
                            type="text"
                            value={categoryConfig?.[field.key] || ''}
                            onChange={(e) => setForm((prev) => ({
                              ...prev,
                              pipelines: {
                                ...prev.pipelines,
                                services: {
                                  ...prev.pipelines.services,
                                  [serviceId]: {
                                    ...prev.pipelines.services[serviceId],
                                    [category]: { ...categoryConfig, [field.key]: e.target.value },
                                  },
                                },
                              },
                            }))}
                            placeholder={field.placeholder || ''}
                            className="flex-1 px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                          />
                          {/* Browse button for Jenkins and ArgoCD */}
                          {(categoryConfig?.provider === 'jenkins' && field.key === 'jobPath') ||
                           (categoryConfig?.provider === 'argocd' && field.key === 'appName') ? (
                            <button
                              type="button"
                              onClick={() => openPipelineDiscovery(
                                categoryConfig.provider,
                                serviceId,
                                category,
                                field.key
                              )}
                              className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded text-xs flex items-center gap-1"
                              title="Browse available pipelines"
                            >
                              <Search size={12} />
                            </button>
                          ) : null}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              );
            };

            return (
              <div className="space-y-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <label className="text-sm font-medium text-gray-300">Services</label>
                  <div className="flex items-center gap-2">
                    {missingServices.length > 0 && (
                      <button
                        type="button"
                        onClick={() => {
                          setForm((prev) => {
                            const newServices = { ...(prev.pipelines?.services || {}) };
                            missingServices.forEach((id) => {
                              newServices[id] = {
                                build: { enabled: true, provider: 'jenkins' },
                              };
                            });
                            return {
                              ...prev,
                              pipelines: { ...prev.pipelines, services: newServices },
                            };
                          });
                        }}
                        className="flex items-center gap-1 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded"
                      >
                        <Layers size={14} />
                        Import from topology ({missingServices.length})
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        const newServiceId = `service-${serviceEntries.length + 1}`;
                        setForm((prev) => ({
                          ...prev,
                          pipelines: {
                            ...prev.pipelines,
                            services: {
                              ...(prev.pipelines?.services || {}),
                              [newServiceId]: {
                                build: { enabled: false, provider: 'jenkins' },
                                deploy: { enabled: false, provider: 'jenkins' },
                              },
                            },
                          },
                        }));
                      }}
                      className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded"
                    >
                      <Plus size={14} />
                      Add Service
                    </button>
                  </div>
                </div>

                {serviceEntries.length === 0 ? (
                  <p className="text-xs text-gray-500">
                    No services configured.
                    {workloadComponents.length > 0
                      ? ` Click "Import from topology" to add ${workloadComponents.length} service(s) from the topology.`
                      : ' Add a service to enable pipeline features.'}
                  </p>
                ) : (
                  <div className="space-y-3">
                    {serviceEntries.map(([serviceId, config]) => (
                      <div
                        key={serviceId}
                        className="bg-gray-800/60 border border-gray-800 rounded-lg p-4 space-y-3"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={serviceId}
                              onChange={(e) => {
                                const newId = e.target.value.trim();
                                if (!newId || newId === serviceId) return;
                                setForm((prev) => {
                                  const { [serviceId]: oldConfig, ...rest } = prev.pipelines?.services || {};
                                  return {
                                    ...prev,
                                    pipelines: {
                                      ...prev.pipelines,
                                      services: { ...rest, [newId]: oldConfig },
                                    },
                                  };
                                });
                              }}
                              list="topology-component-ids"
                              placeholder="service-name"
                              className="px-2 py-1 bg-gray-900 border border-gray-700 rounded text-sm font-medium text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                            />
                            <datalist id="topology-component-ids">
                              {topologyComponents.map((id) => (
                                <option key={id} value={id} />
                              ))}
                            </datalist>
                          </div>
                          <button
                            type="button"
                            onClick={() => setForm((prev) => {
                              const { [serviceId]: _, ...rest } = prev.pipelines?.services || {};
                              return {
                                ...prev,
                                pipelines: { ...prev.pipelines, services: rest },
                              };
                            })}
                            className="text-red-400 hover:text-red-300"
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>

                        {/* Build section only (deploy is per environment) */}
                        {(() => {
                          const category = 'build';
                          const categoryConfig = config?.[category] || {};
                          const isEnabled = categoryConfig?.enabled || false;

                          return (
                            <div className={`p-3 rounded-lg border ${isEnabled ? 'bg-gray-900/60 border-gray-700' : 'bg-gray-900/30 border-gray-800'}`}>
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
                                    onChange={(e) => setForm((prev) => ({
                                      ...prev,
                                      pipelines: {
                                        ...prev.pipelines,
                                        services: {
                                          ...prev.pipelines.services,
                                          [serviceId]: {
                                            ...config,
                                            [category]: {
                                              ...categoryConfig,
                                              enabled: e.target.checked,
                                              provider: e.target.checked ? (categoryConfig?.provider || 'jenkins') : categoryConfig?.provider,
                                            },
                                          },
                                        },
                                      },
                                    }))}
                                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500"
                                  />
                                </label>
                              </div>

                              {isEnabled && (
                                <div className="space-y-2">
                                  <div>
                                    <label className="block text-[10px] font-medium text-gray-500 mb-0.5">Provider</label>
                                    <select
                                      value={categoryConfig?.provider || 'jenkins'}
                                      onChange={(e) => {
                                        const newProvider = e.target.value;
                                        setForm((prev) => ({
                                          ...prev,
                                          pipelines: {
                                            ...prev.pipelines,
                                            services: {
                                              ...prev.pipelines.services,
                                              [serviceId]: {
                                                ...config,
                                                [category]: { enabled: true, provider: newProvider },
                                              },
                                            },
                                          },
                                        }));
                                      }}
                                      className="w-full px-2 py-1 bg-gray-900 border border-gray-700 rounded text-xs text-white focus:border-blue-500 focus:outline-none"
                                    >
                                      {PIPELINE_PROVIDER_TYPES.map((opt) => (
                                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                                      ))}
                                    </select>
                                  </div>
                                  {renderProviderFields(serviceId, category, categoryConfig)}
                                </div>
                              )}
                            </div>
                          );
                        })()}

                        <p className="text-[10px] text-gray-500">
                          Deploy pipelines are configured per environment
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-4 border-t border-gray-800">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            {isEdit ? 'Save Changes' : 'Create Project'}
          </button>
          <Link
            to="/admin/config/projects"
            className="px-4 py-2 text-gray-400 hover:text-white"
          >
            Cancel
          </Link>
        </div>
      </form>

      {/* Environments link for edit mode */}
      {isEdit && (
        <div className="mt-8 p-4 bg-gray-900 border border-gray-800 rounded-lg">
          <h3 className="text-sm font-medium text-white mb-2">Environments</h3>
          <p className="text-sm text-gray-500 mb-3">
            Manage environments for this project
          </p>
          <Link
            to={`/admin/config/projects/${projectId}/environments`}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
          >
            <FolderKanban size={16} />
            Manage Environments
          </Link>
        </div>
      )}

      {/* Pipeline Discovery Modal */}
      {pipelineDiscovery.open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <div>
                <h3 className="text-lg font-semibold text-white">
                  Browse {pipelineDiscovery.provider === 'jenkins' ? 'Jenkins Jobs' : 'ArgoCD Applications'}
                </h3>
                <p className="text-xs text-gray-500 mt-1">
                  {pipelineDiscovery.provider === 'jenkins'
                    ? `Current path: ${pipelineDiscovery.currentPath || '/'}`
                    : 'Select an application'}
                </p>
              </div>
              <button
                onClick={closePipelineDiscovery}
                className="p-1 hover:bg-gray-700 rounded"
              >
                <X size={20} className="text-gray-400" />
              </button>
            </div>

            {/* Search filter */}
            <div className="px-4 py-2 border-b border-gray-700">
              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={pipelineDiscovery.filter}
                  onChange={(e) => setPipelineDiscovery(prev => ({ ...prev, filter: e.target.value }))}
                  placeholder="Filter items..."
                  className="w-full pl-9 pr-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-4">
              {pipelineDiscovery.loading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw size={24} className="animate-spin text-gray-500" />
                </div>
              ) : pipelineDiscovery.error ? (
                <div className="text-center py-8">
                  <AlertCircle size={32} className="mx-auto text-red-400 mb-2" />
                  <p className="text-red-400">{pipelineDiscovery.error}</p>
                  <button
                    onClick={() => discoverPipelines(pipelineDiscovery.provider, pipelineDiscovery.currentPath)}
                    className="mt-4 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded"
                  >
                    Retry
                  </button>
                </div>
              ) : pipelineDiscovery.items.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  No items found
                </div>
              ) : (() => {
                // Filter items based on search
                const filterText = pipelineDiscovery.filter.toLowerCase();
                const filteredItems = filterText
                  ? pipelineDiscovery.items.filter(item =>
                      item.name.toLowerCase().includes(filterText) ||
                      (item.path && item.path.toLowerCase().includes(filterText))
                    )
                  : pipelineDiscovery.items;

                if (filteredItems.length === 0) {
                  return (
                    <div className="text-center py-8 text-gray-500">
                      No items match "{pipelineDiscovery.filter}"
                    </div>
                  );
                }

                return (
                <div className="space-y-1">
                  {/* Back button for Jenkins folders */}
                  {pipelineDiscovery.provider === 'jenkins' && pipelineDiscovery.currentPath !== '/' && (
                    <button
                      onClick={() => {
                        const parts = pipelineDiscovery.currentPath.split('/').filter(Boolean);
                        parts.pop();
                        navigateToFolder(parts.length > 0 ? parts.join('/') : '/');
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 hover:bg-gray-800 rounded text-left"
                    >
                      <FolderOpen size={16} className="text-yellow-400" />
                      <span className="text-gray-400">..</span>
                    </button>
                  )}

                  {/* Items list */}
                  {filteredItems.map((item, index) => (
                    <div
                      key={`${item.path}-${index}`}
                      className="flex items-center gap-2 px-3 py-2 hover:bg-gray-800 rounded cursor-pointer group"
                      onClick={() => {
                        if (item.type === 'folder') {
                          navigateToFolder(item.path);
                        } else {
                          selectPipelineItem(item);
                        }
                      }}
                    >
                      {item.type === 'folder' ? (
                        <Folder size={16} className="text-yellow-400" />
                      ) : pipelineDiscovery.provider === 'argocd' ? (
                        <GitBranch size={16} className="text-green-400" />
                      ) : (
                        <GitBranch size={16} className="text-blue-400" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-white truncate">{item.name}</div>
                        {item.type !== 'folder' && (
                          <div className="text-xs text-gray-500 truncate">{item.path}</div>
                        )}
                        {/* ArgoCD specific info */}
                        {item.status && (
                          <div className="text-xs text-gray-500 flex items-center gap-2 mt-0.5">
                            <span className={item.status.health === 'Healthy' ? 'text-green-400' : item.status.health === 'Degraded' ? 'text-red-400' : 'text-yellow-400'}>
                              {item.status.health}
                            </span>
                            <span className={item.status.sync === 'Synced' ? 'text-green-400' : 'text-yellow-400'}>
                              {item.status.sync}
                            </span>
                          </div>
                        )}
                      </div>
                      {item.type === 'folder' ? (
                        <ChevronRight size={16} className="text-gray-500 opacity-0 group-hover:opacity-100" />
                      ) : (
                        <span className="text-xs text-blue-400 opacity-0 group-hover:opacity-100">Select</span>
                      )}
                    </div>
                  ))}
                </div>
                );
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
