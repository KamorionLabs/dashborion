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
    </div>
  );
}
