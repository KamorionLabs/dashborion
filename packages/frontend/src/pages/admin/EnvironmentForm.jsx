/**
 * EnvironmentForm - Create/Edit Environment (Wizard)
 */
import { useMemo, useEffect, useState } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  AlertCircle,
  CheckCircle,
  XCircle,
  ChevronRight,
  ChevronLeft,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Compass,
  ShieldCheck,
  Layers,
  Radar,
  ClipboardCheck,
  Cloud,
  Server,
  Network,
  Tag,
  Globe,
  Info,
  GitBranch,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';
import { useConfig } from '../../ConfigContext';
import ResourcePicker from '../../components/admin/ResourcePicker';
import { stripServiceName } from '../../utils/serviceNaming';
import { PipelineConfigSection } from '../../components/admin/pipelines';

const AWS_REGIONS = [
  { value: 'eu-central-1', label: 'EU (Frankfurt)' },
  { value: 'eu-west-1', label: 'EU (Ireland)' },
  { value: 'eu-west-2', label: 'EU (London)' },
  { value: 'eu-west-3', label: 'EU (Paris)' },
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'us-west-2', label: 'US West (Oregon)' },
];

const STATUS_OPTIONS = ['planned', 'active', 'deployed', 'deprecated'];

const INFRA_RESOURCE_CONFIGS = [
  { key: 'network', label: 'Network (VPC)', pickerType: 'vpc', idLabel: 'VPC ID' },
  { key: 'alb', label: 'ALB', pickerType: 'alb', idLabel: 'ALB ARN' },
  { key: 'rds', label: 'RDS/Aurora', pickerType: 'rds', idLabel: 'DB Identifier' },
  { key: 'redis', label: 'ElastiCache', pickerType: 'elasticache', idLabel: 'Cluster ID' },
  { key: 'efs', label: 'EFS', pickerType: 'efs', idLabel: 'File System ID' },
  { key: 's3', label: 'S3', pickerType: 's3', idLabel: 'Bucket Name' },
  { key: 'cloudfront', label: 'CloudFront', pickerType: 'cloudfront', idLabel: 'Distribution ID' },
];


const STEPS = [
  {
    id: 'context',
    label: 'Context',
    icon: Compass,
    description: 'Define the AWS account, region, and target cluster for this environment.',
  },
  {
    id: 'access',
    label: 'Access',
    icon: ShieldCheck,
    description: 'Optional override of the IAM roles used for discovery and actions.',
  },
  {
    id: 'services',
    label: 'Service Discovery',
    icon: Layers,
    description: 'Discover services in ECS/EKS and select what to monitor.',
  },
  {
    id: 'pipelines',
    label: 'Pipelines',
    icon: GitBranch,
    description: 'Configure build and deploy pipelines for services.',
  },
  {
    id: 'discovery',
    label: 'Discovery',
    icon: Radar,
    description: 'Configure tags/IDs and preview discovered resources.',
  },
  {
    id: 'review',
    label: 'Review',
    icon: ClipboardCheck,
    description: 'Final validation before saving.',
  },
];

const clampStep = (value) => Math.min(Math.max(value, 0), STEPS.length - 1);

export default function EnvironmentForm() {
  const { projectId, envId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const isEdit = Boolean(envId);
  const config = useConfig();

  const [wizardStep, setWizardStep] = useState(() => {
    const stepParam = Number(searchParams.get('step') || 0);
    return clampStep(stepParam);
  });

  useEffect(() => {
    setSearchParams({ step: String(wizardStep) }, { replace: true });
  }, [wizardStep, setSearchParams]);

  useEffect(() => {
    const stepParam = Number(searchParams.get('step') || 0);
    const nextStep = clampStep(stepParam);
    setWizardStep((prev) => (prev === nextStep ? prev : nextStep));
  }, [searchParams]);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [awsAccounts, setAwsAccounts] = useState([]);
  const [clusters, setClusters] = useState([]);
  const [project, setProject] = useState(null);

  const [form, setForm] = useState({
    envId: '',
    displayName: '',
    status: 'planned',
    accountId: '',
    region: 'eu-central-1',
    clusterName: '',
    namespace: '',
    services: [],
    readRoleArn: '',
    actionRoleArn: '',
    enabled: true,
    infrastructure: {
      defaultTags: {},
      domainConfig: {},
      resources: {},
    },
    checkers: {},
    pipelines: { services: {} },
  });

  const [servicePickerValue, setServicePickerValue] = useState('');

  const [discoveryData, setDiscoveryData] = useState(null);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [discoveryError, setDiscoveryError] = useState(null);

  const [tagSuggestions, setTagSuggestions] = useState([]);
  const [tagDiscoveryLoading, setTagDiscoveryLoading] = useState(false);
  const [tagDiscoveryError, setTagDiscoveryError] = useState(null);

  const [testingRead, setTestingRead] = useState(false);
  const [testingAction, setTestingAction] = useState(false);
  const [readTestResult, setReadTestResult] = useState(null);
  const [actionTestResult, setActionTestResult] = useState(null);

  const [newService, setNewService] = useState('');
  const [newTagKey, setNewTagKey] = useState('');
  const [newTagValue, setNewTagValue] = useState('');
  const [newDomainKey, setNewDomainKey] = useState('');
  const [newDomainValue, setNewDomainValue] = useState('');
  const [resourceIdDrafts, setResourceIdDrafts] = useState({});
  const [resourceTagDrafts, setResourceTagDrafts] = useState({});


  function normalizeDiscoveredServiceName(serviceName, envOverride = '') {
    const envValue = envOverride || form.envId || envId || '';
    return stripServiceName(serviceName, config?.serviceNaming, projectId, envValue);
  }

  useEffect(() => {
    loadResources();
  }, []);

  useEffect(() => {
    if (isEdit) {
      loadEnvironment();
    }
  }, [envId]);

  const loadResources = async () => {
    try {
      const [accountsRes, projectRes, clustersRes] = await Promise.all([
        fetchWithRetry('/api/config/aws-accounts'),
        fetchWithRetry(`/api/config/projects/${projectId}`),
        fetchWithRetry('/api/config/clusters'),
      ]);

      if (accountsRes.ok) {
        const data = await accountsRes.json();
        setAwsAccounts(data.awsAccounts || []);
      }
      if (projectRes.ok) {
        const data = await projectRes.json();
        setProject(data);
      }
      if (clustersRes.ok) {
        const data = await clustersRes.json();
        setClusters(data.clusters || []);
      }
    } catch (err) {
      console.error('Error loading resources:', err);
    }
  };

  const loadEnvironment = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(
        `/api/config/projects/${projectId}/environments/${envId}`
      );

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Environment not found');
        }
        throw new Error('Failed to load environment');
      }

      const data = await response.json();
      const infra = data.infrastructure || {};
      const resources = {};
      Object.entries(infra.resources || {}).forEach(([key, value]) => {
        resources[key] = {
          ids: value?.ids || [],
          tags: value?.tags || {},
        };
      });

      const normalizedServices = (data.services || []).map((svc) =>
        normalizeDiscoveredServiceName(svc, data.envId || envId)
      );

      setForm({
        envId: data.envId || '',
        displayName: data.displayName || '',
        status: data.status || 'planned',
        accountId: data.accountId || '',
        region: data.region || 'eu-central-1',
        clusterName: data.clusterName || '',
        namespace: data.namespace || '',
        services: normalizedServices,
        readRoleArn: data.readRoleArn || '',
        actionRoleArn: data.actionRoleArn || '',
        enabled: data.enabled !== false,
        infrastructure: {
          defaultTags: infra.defaultTags || {},
          domainConfig: infra.domainConfig || {},
          resources,
        },
        checkers: data.checkers || {},
        pipelines: data.pipelines || { services: {} },
      });
    } catch (err) {
      console.error('Error loading environment:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const normalizeInfrastructure = (infra) => {
    if (!infra) return {};
    const resources = {};
    Object.entries(infra.resources || {}).forEach(([key, value]) => {
      const ids = Array.isArray(value?.ids) ? value.ids.filter(Boolean) : [];
      const tags = value?.tags && typeof value.tags === 'object' ? value.tags : {};
      if (ids.length || Object.keys(tags).length) {
        resources[key] = { ids, tags };
      }
    });

    const result = {};
    if (infra.defaultTags && Object.keys(infra.defaultTags).length) {
      result.defaultTags = infra.defaultTags;
    }
    if (infra.domainConfig && Object.keys(infra.domainConfig).length) {
      result.domainConfig = infra.domainConfig;
    }
    if (Object.keys(resources).length) {
      result.resources = resources;
    }
    return result;
  };
  const updateInfrastructure = (updater) => {
    setForm((prev) => {
      const infra = prev.infrastructure || {};
      const next = updater({
        defaultTags: infra.defaultTags || {},
        domainConfig: infra.domainConfig || {},
        resources: infra.resources || {},
      });
      return { ...prev, infrastructure: next };
    });
  };

  const updateDomainConfig = (updater) => {
    updateInfrastructure((infra) => {
      const domainConfig = infra.domainConfig || {};
      const next = updater({
        pattern: domainConfig.pattern || '',
        domains: domainConfig.domains || {},
      });
      return { ...infra, domainConfig: next };
    });
  };

  const getResourceConfig = (resourceKey) => {
    return form.infrastructure?.resources?.[resourceKey] || { ids: [], tags: {} };
  };

  const updateResourceConfig = (resourceKey, updater) => {
    updateInfrastructure((infra) => {
      const resources = { ...(infra.resources || {}) };
      const current = resources[resourceKey] || { ids: [], tags: {} };
      const updated = updater(current);
      const ids = updated.ids || [];
      const tags = updated.tags || {};
      if (!ids.length && !Object.keys(tags).length) {
        delete resources[resourceKey];
      } else {
        resources[resourceKey] = { ids, tags };
      }
      return { ...infra, resources };
    });
  };

  const saveEnvironment = async ({ redirectAfterCreate = false, silent = false } = {}) => {
    if (!form.envId) {
      setError('Environment ID is required');
      return null;
    }

    setSaving(true);
    if (!silent) {
      setError(null);
    }

    try {
      const method = isEdit ? 'PUT' : 'POST';
      const url = isEdit
        ? `/api/config/projects/${projectId}/environments/${envId}`
        : `/api/config/projects/${projectId}/environments`;

      const payload = {
        ...form,
        infrastructure: normalizeInfrastructure(form.infrastructure),
      };

      const response = await fetchWithRetry(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save environment');
      }

      const data = await response.json();
      if (!isEdit && redirectAfterCreate) {
        navigate(`/admin/config/projects/${projectId}/environments/${form.envId}?step=${wizardStep + 1}`);
      }
      return data;
    } catch (err) {
      console.error('Error saving environment:', err);
      if (!silent) {
        setError(err.message);
      }
      return null;
    } finally {
      setSaving(false);
    }
  };

  const addService = () => {
    if (newService && !form.services.includes(newService)) {
      setForm({ ...form, services: [...form.services, newService] });
      setNewService('');
    }
  };

  const removeService = (service) => {
    setForm({ ...form, services: form.services.filter((s) => s !== service) });
  };

  const clusterOptions = useMemo(() => {
    const accountId = form.accountId;
    const region = form.region;
    const orchestratorType = project?.orchestratorType;

    return clusters.filter((cluster) => {
      const clusterAccount = cluster.awsAccountId || cluster.accountId || '';
      const clusterRegion = cluster.region || '';
      const clusterType = cluster.type || null;

      if (accountId && clusterAccount && clusterAccount !== accountId) return false;
      if (region && clusterRegion && clusterRegion !== region) return false;
      if (orchestratorType && clusterType && clusterType !== orchestratorType) return false;
      return true;
    });
  }, [clusters, form.accountId, form.region, project?.orchestratorType]);

  const getClusterId = (cluster) => cluster.clusterId || cluster.id || cluster.name || '';
  const getClusterName = (cluster) => cluster.clusterName || cluster.name || cluster.clusterId || cluster.id || '';

  const clusterSelectOptions = useMemo(() => {
    return clusterOptions.length > 0 ? clusterOptions : clusters;
  }, [clusterOptions, clusters]);

  const selectedCluster = useMemo(() => {
    return clusterSelectOptions.find((cluster) => {
      const clusterName = getClusterName(cluster);
      const clusterId = getClusterId(cluster);
      return clusterName === form.clusterName || clusterId === form.clusterName;
    }) || null;
  }, [clusterSelectOptions, form.clusterName]);

  const clusterSelectValue = selectedCluster ? getClusterId(selectedCluster) : '';

  const serviceDiscoveryType = project?.orchestratorType === 'ecs' ? 'ecs-services' : 'eks-workloads';
  const serviceDiscoveryDisabled = !form.accountId || !form.clusterName || (project?.orchestratorType !== 'ecs' && !form.namespace);

  const addServiceFromPicker = () => {
    if (!servicePickerValue) return;
    const normalized = normalizeDiscoveredServiceName(servicePickerValue);
    if (!form.services.includes(normalized)) {
      setForm({ ...form, services: [...form.services, normalized] });
    }
    setServicePickerValue('');
  };

  const addTag = () => {
    if (newTagKey && newTagValue) {
      updateInfrastructure((infra) => ({
        ...infra,
        defaultTags: {
          ...infra.defaultTags,
          [newTagKey]: newTagValue,
        },
      }));
      setNewTagKey('');
      setNewTagValue('');
    }
  };

  const addSuggestedTag = (key, value) => {
    if (!key || !value) return;
    updateInfrastructure((infra) => {
      if (infra.defaultTags?.[key]) {
        return infra;
      }
      return {
        ...infra,
        defaultTags: {
          ...(infra.defaultTags || {}),
          [key]: value,
        },
      };
    });
  };

  const removeTag = (key) => {
    updateInfrastructure((infra) => {
      const { [key]: _, ...rest } = infra.defaultTags || {};
      return { ...infra, defaultTags: rest };
    });
  };

  const addDomain = () => {
    if (newDomainKey && newDomainValue) {
      updateDomainConfig((domainConfig) => ({
        ...domainConfig,
        domains: {
          ...(domainConfig.domains || {}),
          [newDomainKey]: newDomainValue,
        },
      }));
      setNewDomainKey('');
      setNewDomainValue('');
    }
  };

  const removeDomain = (key) => {
    updateDomainConfig((domainConfig) => {
      const { [key]: _, ...rest } = domainConfig.domains || {};
      return { ...domainConfig, domains: rest };
    });
  };

  const setResourceIdDraft = (resourceKey, value) => {
    setResourceIdDrafts((prev) => ({ ...prev, [resourceKey]: value }));
  };

  const addResourceId = (resourceKey) => {
    const value = (resourceIdDrafts[resourceKey] || '').trim();
    if (!value) return;
    updateResourceConfig(resourceKey, (current) => ({
      ...current,
      ids: [...(current.ids || []), value],
    }));
    setResourceIdDraft(resourceKey, '');
  };

  const removeResourceId = (resourceKey, value) => {
    updateResourceConfig(resourceKey, (current) => ({
      ...current,
      ids: (current.ids || []).filter((id) => id !== value),
    }));
  };

  const setResourceTagDraft = (resourceKey, field, value) => {
    setResourceTagDrafts((prev) => ({
      ...prev,
      [resourceKey]: {
        ...(prev[resourceKey] || { key: '', value: '' }),
        [field]: value,
      },
    }));
  };

  const addResourceTag = (resourceKey) => {
    const draft = resourceTagDrafts[resourceKey] || {};
    const key = (draft.key || '').trim();
    const value = (draft.value || '').trim();
    if (!key || !value) return;
    updateResourceConfig(resourceKey, (current) => ({
      ...current,
      tags: { ...(current.tags || {}), [key]: value },
    }));
    setResourceTagDraft(resourceKey, 'key', '');
    setResourceTagDraft(resourceKey, 'value', '');
  };

  const removeResourceTag = (resourceKey, tagKey) => {
    updateResourceConfig(resourceKey, (current) => {
      const { [tagKey]: _, ...rest } = current.tags || {};
      return { ...current, tags: rest };
    });
  };

  const discoverTags = async () => {
    if (!form.accountId) {
      setTagDiscoveryError('Select an AWS account first');
      return;
    }

    setTagDiscoveryLoading(true);
    setTagDiscoveryError(null);
    setTagSuggestions([]);

    const resourceTypes = ['vpc', 'alb', 'efs'];
    if (project?.orchestratorType === 'ecs') {
      resourceTypes.push('ecs');
    } else if (project?.orchestratorType === 'eks') {
      resourceTypes.push('eks');
    }

    try {
      const requests = resourceTypes.map((resourceType) => {
        const params = new URLSearchParams();
        if (form.region) params.set('region', form.region);
        const url = `/api/config/discovery/${form.accountId}/${resourceType}?${params.toString()}`;
        return fetchWithRetry(url)
          .then((res) => res.json())
          .then((data) => data.resources || []);
      });

      const results = await Promise.allSettled(requests);
      const counts = new Map();

      results.forEach((result) => {
        if (result.status !== 'fulfilled') return;
        result.value.forEach((resource) => {
          const tags = resource.tags || {};
          Object.entries(tags).forEach(([key, value]) => {
            const normalizedValue = String(value);
            const signature = `${key}:${normalizedValue}`;
            counts.set(signature, {
              key,
              value: normalizedValue,
              count: (counts.get(signature)?.count || 0) + 1,
            });
          });
        });
      });

      const suggestions = Array.from(counts.values())
        .sort((a, b) => b.count - a.count)
        .slice(0, 16);

      setTagSuggestions(suggestions);
    } catch (err) {
      setTagDiscoveryError(err.message || 'Tag discovery failed');
    } finally {
      setTagDiscoveryLoading(false);
    }
  };

  const testRole = async (roleArn, setTesting, setResult) => {
    if (!roleArn) return;
    setTesting(true);
    setResult(null);
    try {
      const response = await fetchWithRetry(
        `/api/config/discovery/test-role?roleArn=${encodeURIComponent(roleArn)}`
      );
      const data = await response.json();
      setResult(data);
    } catch (err) {
      console.error('Test role error:', err);
      setResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleTestReadRole = () => {
    testRole(form.readRoleArn, setTestingRead, setReadTestResult);
  };

  const handleTestActionRole = () => {
    testRole(form.actionRoleArn, setTestingAction, setActionTestResult);
  };

  const TestResultBadge = ({ result, testing }) => {
    if (testing) {
      return <RefreshCw size={14} className="animate-spin text-gray-400" />;
    }
    if (!result) return null;
    if (result.success) {
      return <CheckCircle size={14} className="text-green-400" />;
    }
    return <XCircle size={14} className="text-red-400" />;
  };

  const fetchInfrastructureSnapshot = async (envKey) => {
    const baseUrl = `/api/${projectId}/infrastructure/${envKey}`;
    const endpoints = {
      meta: `${baseUrl}/meta?force=true`,
      cloudfront: `${baseUrl}/cloudfront?force=true`,
      alb: `${baseUrl}/alb?force=true`,
      rds: `${baseUrl}/rds?force=true`,
      redis: `${baseUrl}/redis?force=true`,
      efs: `${baseUrl}/efs?force=true`,
      s3: `${baseUrl}/s3?force=true`,
      workloads: `${baseUrl}/workloads?force=true`,
    };

    const entries = Object.entries(endpoints);
    const results = await Promise.allSettled(
      entries.map(([_, url]) => fetchWithRetry(url).then((res) => res.json()))
    );

    const data = {};
    results.forEach((result, index) => {
      const key = entries[index][0];
      if (result.status === 'fulfilled') {
        Object.assign(data, result.value);
      } else {
        console.error(`Discovery fetch failed: ${key}`, result.reason);
      }
    });
    return data;
  };

  const runDiscovery = async () => {
    setDiscoveryLoading(true);
    setDiscoveryError(null);

    const saved = await saveEnvironment({ silent: true });
    if (!saved) {
      setDiscoveryLoading(false);
      return;
    }

    try {
      const data = await fetchInfrastructureSnapshot(form.envId);
      setDiscoveryData(data);
    } catch (err) {
      console.error('Discovery failed:', err);
      setDiscoveryError(err.message || 'Discovery failed');
    } finally {
      setDiscoveryLoading(false);
    }
  };

  const addDiscoveredIds = (resourceKey, ids) => {
    if (!ids || ids.length === 0) return;
    updateResourceConfig(resourceKey, (current) => {
      const existing = new Set(current.ids || []);
      ids.forEach((id) => existing.add(id));
      return { ...current, ids: Array.from(existing) };
    });
  };

  const discoveredCloudfrontIds = useMemo(() => {
    const cf = discoveryData?.cloudfront;
    if (!cf) return [];
    if (cf.distributions && Array.isArray(cf.distributions)) {
      return cf.distributions.map((dist) => dist.id).filter(Boolean);
    }
    if (cf.id) return [cf.id];
    return [];
  }, [discoveryData]);

  const discoveredAlbIds = useMemo(() => {
    const alb = discoveryData?.alb;
    if (!alb) return [];
    if (alb.arn) return [alb.arn];
    return [];
  }, [discoveryData]);

  const discoveredRdsIds = useMemo(() => {
    const rds = discoveryData?.rds;
    if (!rds) return [];
    if (rds.identifier) return [rds.identifier];
    return [];
  }, [discoveryData]);

  const discoveredRedisIds = useMemo(() => {
    const redis = discoveryData?.redis;
    if (!redis) return [];
    if (redis.clusterId) return [redis.clusterId];
    return [];
  }, [discoveryData]);

  const discoveredEfsIds = useMemo(() => {
    const efs = discoveryData?.efs;
    if (!efs) return [];
    if (efs.fileSystemId) return [efs.fileSystemId];
    return [];
  }, [discoveryData]);


  const renderStepHeader = () => (
    <div className="flex flex-wrap gap-2">
      {STEPS.map((step, index) => {
        const isActive = index === wizardStep;
        const isComplete = index < wizardStep;
        const isLocked = !isEdit && index > 0;
        const Icon = step.icon;
        return (
          <button
            key={step.id}
            type="button"
            disabled={isLocked}
            onClick={() => setWizardStep(index)}
            className={`px-3 py-1.5 rounded-full text-sm transition-colors ${
              isActive
                ? 'bg-blue-600 text-white'
                : isComplete
                  ? 'bg-blue-600/20 text-blue-300'
                  : 'bg-gray-800 text-gray-400'
            } ${isLocked ? 'opacity-50 cursor-not-allowed' : 'hover:bg-gray-700'}`}
          >
            <span className="inline-flex items-center gap-2">
              {Icon && <Icon size={14} />}
              {step.label}
            </span>
          </button>
        );
      })}
    </div>
  );

  const renderStepActions = () => {
    const isFirst = wizardStep === 0;
    const isLast = wizardStep === STEPS.length - 1;
    const canGoNext = true;
    return (
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          disabled={isFirst}
          onClick={() => setWizardStep((prev) => clampStep(prev - 1))}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700 disabled:opacity-50"
        >
          <ChevronLeft size={16} />
          Back
        </button>

        <div className="flex items-center gap-2">
          {isEdit && (
            <button
              type="button"
              onClick={() => saveEnvironment({})}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 text-gray-200 hover:bg-gray-700"
            >
              <Save size={16} />
              Save
            </button>
          )}
          {isLast ? (
            <button
              type="button"
              onClick={async () => {
                const saved = await saveEnvironment({});
                if (saved) {
                  navigate(`/admin/config/projects/${projectId}/environments`);
                }
              }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-500"
            >
              <CheckCircle size={16} />
              Finish
            </button>
          ) : (
            <button
              type="button"
              disabled={!canGoNext}
              onClick={async () => {
                const saved = await saveEnvironment({ redirectAfterCreate: !isEdit && wizardStep === 0, silent: true });
                if (!saved) return;
                if (!isEdit && wizardStep === 0) return;
                setWizardStep((prev) => clampStep(prev + 1));
              }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
            >
              Save & continue
              <ChevronRight size={16} />
            </button>
          )}
        </div>
      </div>
    );
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
    <div className="p-6 space-y-6">
      <div className="mb-2">
        <Link
          to={`/admin/config/projects/${projectId}/environments`}
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft size={16} />
          Back to Environments
        </Link>
        <h1 className="text-2xl font-semibold text-white">
          {isEdit ? `Edit ${form.displayName || envId}` : 'Create Environment'}
        </h1>
        <p className="text-gray-500">
          {project?.displayName || projectId}
        </p>
      </div>

      {error && (
        <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg flex items-center gap-3">
          <AlertCircle size={20} className="text-red-400" />
          <span className="text-red-400">{error}</span>
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        {renderStepHeader()}
      </div>
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex items-center gap-3">
        {STEPS[wizardStep]?.icon && (
          <div className="h-9 w-9 rounded-lg bg-gray-800 flex items-center justify-center text-blue-300">
            {(() => {
              const Icon = STEPS[wizardStep].icon;
              return <Icon size={18} />;
            })()}
          </div>
        )}
        <div>
          <div className="text-sm text-gray-200 font-medium">{STEPS[wizardStep]?.label}</div>
          <div className="text-xs text-gray-500">{STEPS[wizardStep]?.description}</div>
        </div>
      </div>

      {wizardStep === 0 && (
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Compass size={18} className="text-blue-400" />
              Basic Info
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Environment ID <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={form.envId}
                  onChange={(e) => setForm({ ...form, envId: e.target.value })}
                  disabled={isEdit}
                  placeholder="staging, production, nh-ppd"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
                />
                <p className="mt-1 text-xs text-gray-500">
                  Used in URLs and logical names. Cannot be changed after creation.
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Display Name
                </label>
                <input
                  type="text"
                  value={form.displayName}
                  onChange={(e) => setForm({ ...form, displayName: e.target.value })}
                  placeholder="Staging Environment"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <p className="mt-1 text-xs text-gray-500">Shown in the UI.</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Status
                </label>
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500">Controls the status badge on the dashboard.</p>
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="enabled"
                  checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-700 bg-gray-800"
                />
                <label htmlFor="enabled" className="text-sm text-gray-300">
                  Enabled
                </label>
              </div>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Cloud size={18} className="text-blue-400" />
              AWS Account & Region
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">AWS Account</label>
                <select
                  value={form.accountId}
                  onChange={(e) => setForm({ ...form, accountId: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  <option value="">Select account...</option>
                  {awsAccounts.map((account) => (
                    <option key={account.accountId} value={account.accountId}>
                      {account.displayName || account.accountId}
                    </option>
                  ))}
                </select>
                {awsAccounts.length === 0 && (
                  <p className="mt-2 text-xs text-yellow-400">
                    No AWS accounts configured. <Link to="/admin/config/accounts/new" className="underline">Add an account</Link>
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Region</label>
                <select
                  value={form.region}
                  onChange={(e) => setForm({ ...form, region: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                >
                  {AWS_REGIONS.map((region) => (
                    <option key={region.value} value={region.value}>{region.label}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-gray-500">Primary region for discovery and console links.</p>
              </div>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Server size={18} className="text-blue-400" />
              Cluster
            </h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Cluster Name</label>
                {clusterSelectOptions.length > 0 ? (
                  <select
                    value={clusterSelectValue}
                    onChange={(e) => {
                      const cluster = clusterSelectOptions.find((item) => getClusterId(item) === e.target.value);
                      const name = cluster ? getClusterName(cluster) : '';
                      setForm({ ...form, clusterName: name });
                    }}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="">Select cluster...</option>
                    {clusterSelectOptions.map((cluster) => {
                      const clusterId = getClusterId(cluster);
                      return (
                        <option key={clusterId} value={clusterId}>
                          {cluster.displayName || getClusterName(cluster) || clusterId}
                        </option>
                      );
                    })}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={form.clusterName}
                    onChange={(e) => setForm({ ...form, clusterName: e.target.value })}
                    placeholder="my-cluster"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  />
                )}
                {clusters.length === 0 ? (
                  <p className="mt-2 text-xs text-yellow-400">
                    No clusters configured. <Link to="/admin/config/clusters/new" className="underline">Add a cluster</Link>
                  </p>
                ) : clusterOptions.length === 0 ? (
                  <p className="mt-2 text-xs text-yellow-400">
                    No clusters match the selected account/region/type. Showing all clusters.
                  </p>
                ) : null}
                <p className="mt-1 text-xs text-gray-500">
                  Target cluster (ECS/EKS). Filtered by account and region.
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Namespace (EKS)</label>
                <input
                  type="text"
                  value={form.namespace}
                  onChange={(e) => setForm({ ...form, namespace: e.target.value })}
                  placeholder="default"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
                <p className="mt-1 text-xs text-gray-500">Required for EKS discovery.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {wizardStep === 1 && (
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
              <ShieldCheck size={18} className="text-blue-400" />
              IAM Roles
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Optional. Override the default roles from AWS Account configuration.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Read Role ARN
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={form.readRoleArn}
                    onChange={(e) => setForm({ ...form, readRoleArn: e.target.value })}
                    placeholder="arn:aws:iam::123456789012:role/..."
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleTestReadRole}
                    disabled={!form.readRoleArn || testingRead}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                    title="Test role assumption"
                  >
                    Test
                    <TestResultBadge result={readTestResult} testing={testingRead} />
                  </button>
                </div>
                {readTestResult && (
                  <p className={`mt-2 text-xs ${readTestResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {readTestResult.success
                      ? `Assumed: ${readTestResult.arn}`
                      : `Error: ${readTestResult.error}`}
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Action Role ARN
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={form.actionRoleArn}
                    onChange={(e) => setForm({ ...form, actionRoleArn: e.target.value })}
                    placeholder="arn:aws:iam::123456789012:role/..."
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleTestActionRole}
                    disabled={!form.actionRoleArn || testingAction}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800 text-gray-200 hover:bg-gray-700 disabled:opacity-50"
                    title="Test role assumption"
                  >
                    Test
                    <TestResultBadge result={actionTestResult} testing={testingAction} />
                  </button>
                </div>
                {actionTestResult && (
                  <p className={`mt-2 text-xs ${actionTestResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {actionTestResult.success
                      ? `Assumed: ${actionTestResult.arn}`
                      : `Error: ${actionTestResult.error}`}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {wizardStep === 2 && (
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Network size={18} className="text-blue-400" />
              Service Discovery
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Discover services in your cluster and select the ones to monitor.
            </p>

            {form.services.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {form.services.map((service) => (
                  <span
                    key={service}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-sm text-gray-300"
                  >
                    {service}
                    <button
                      type="button"
                      onClick={() => removeService(service)}
                      className="text-gray-500 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-center gap-2">
              <ResourcePicker
                accountId={form.accountId}
                region={form.region}
                resourceType={serviceDiscoveryType}
                cluster={form.clusterName}
                namespace={form.namespace}
                value={servicePickerValue}
                onChange={setServicePickerValue}
                placeholder="Select discovered service..."
                disabled={serviceDiscoveryDisabled}
                className="flex-1"
              />
              <button
                type="button"
                onClick={addServiceFromPicker}
                disabled={!servicePickerValue}
                className="px-3 py-2 bg-gray-800 text-gray-200 rounded-lg hover:bg-gray-700 disabled:opacity-50"
              >
                Add
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Requires an AWS account + cluster, and a namespace for EKS.
            </p>
            <div className="mt-4 border-t border-gray-800 pt-4">
              <p className="text-xs text-gray-500 mb-2">Manual entry (optional)</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newService}
                  onChange={(e) => setNewService(e.target.value)}
                  placeholder="frontend, backend, cms"
                  className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addService())}
                />
                <button
                  type="button"
                  onClick={addService}
                  className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                >
                  <Plus size={16} />
                </button>
              </div>
              <p className="mt-2 text-xs text-gray-500">Use this for services that cannot be discovered.</p>
            </div>
          </div>
        </div>
      )}

      {wizardStep === 3 && (
        <PipelineConfigSection
          services={form.services}
          pipelines={form.pipelines || { services: {} }}
          project={project}
          onPipelinesChange={(pipelines) => setForm(prev => ({ ...prev, pipelines }))}
        />
      )}

      {wizardStep === 4 && (
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Tag size={18} className="text-blue-400" />
              Default Tags
            </h2>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newTagKey}
                onChange={(e) => setNewTagKey(e.target.value)}
                placeholder="Key"
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
              <input
                type="text"
                value={newTagValue}
                onChange={(e) => setNewTagValue(e.target.value)}
                placeholder="Value"
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
              />
              <button
                type="button"
                onClick={addTag}
                className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
              >
                <Plus size={16} />
              </button>
              <button
                type="button"
                onClick={discoverTags}
                disabled={tagDiscoveryLoading}
                className="px-3 py-2 bg-gray-800 text-gray-200 rounded-lg hover:bg-gray-700 disabled:opacity-50"
                title="Discover tags from existing resources"
              >
                <RefreshCw size={16} className={tagDiscoveryLoading ? 'animate-spin' : ''} />
              </button>
            </div>
            <p className="text-xs text-gray-500 mb-2">
              Tags are used as a fallback when no IDs are provided. Use discovery to suggest existing tags.
            </p>
            {Object.keys(form.infrastructure.defaultTags || {}).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(form.infrastructure.defaultTags).map(([key, value]) => (
                  <span
                    key={key}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-sm text-gray-300"
                  >
                    {key}: {value}
                    <button
                      type="button"
                      onClick={() => removeTag(key)}
                      className="text-gray-500 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {tagDiscoveryError && (
              <p className="text-xs text-red-400 mt-2">{tagDiscoveryError}</p>
            )}
            {tagSuggestions.length > 0 && (
              <div className="mt-4">
                <p className="text-xs text-gray-500 mb-2">Suggested tags</p>
                <div className="flex flex-wrap gap-2">
                  {tagSuggestions.map((tag) => (
                    <button
                      key={`${tag.key}:${tag.value}`}
                      type="button"
                      onClick={() => addSuggestedTag(tag.key, tag.value)}
                      className="inline-flex items-center gap-2 px-2 py-1 rounded bg-gray-800 text-gray-200 text-xs hover:bg-gray-700"
                    >
                      {tag.key}: {tag.value}
                      <span className="text-gray-500">({tag.count})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Globe size={18} className="text-blue-400" />
              Domain Config
            </h2>
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Pattern</label>
                <input
                  type="text"
                  value={form.infrastructure.domainConfig?.pattern || ''}
                  onChange={(e) => updateDomainConfig((config) => ({ ...config, pattern: e.target.value }))}
                  placeholder="{service}.{env}.example.com"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={newDomainKey}
                onChange={(e) => setNewDomainKey(e.target.value)}
                placeholder="frontend"
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
              <input
                type="text"
                value={newDomainValue}
                onChange={(e) => setNewDomainValue(e.target.value)}
                placeholder="fr"
                className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addDomain())}
              />
              <button
                type="button"
                onClick={addDomain}
                className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
              >
                <Plus size={16} />
              </button>
            </div>
            {Object.keys(form.infrastructure.domainConfig?.domains || {}).length > 0 && (
              <div className="flex flex-wrap gap-2">
                {Object.entries(form.infrastructure.domainConfig.domains).map(([key, value]) => (
                  <span
                    key={key}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-sm text-gray-300"
                  >
                    {key}: {value}
                    <button
                      type="button"
                      onClick={() => removeDomain(key)}
                      className="text-gray-500 hover:text-red-400"
                    >
                      <Trash2 size={12} />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Server size={18} className="text-blue-400" />
              Resources
            </h2>
            <div className="space-y-6">
              {INFRA_RESOURCE_CONFIGS.map((resource) => {
                const config = getResourceConfig(resource.key);
                const ids = config.ids || [];
                const tags = config.tags || {};
                const draftId = resourceIdDrafts[resource.key] || '';
                const draftTag = resourceTagDrafts[resource.key] || { key: '', value: '' };
                return (
                  <div key={resource.key} className="border border-gray-800 rounded-lg p-4">
                    <h3 className="text-md font-semibold text-white mb-3">{resource.label}</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        {resource.idLabel}
                      </label>
                      <div className="flex gap-2 mb-2">
                          {resource.pickerType ? (
                            <ResourcePicker
                              accountId={form.accountId}
                              resourceType={resource.pickerType}
                              value={draftId}
                              onChange={(value) => setResourceIdDraft(resource.key, value)}
                              placeholder={`Select ${resource.label}...`}
                              region={form.region}
                              disabled={!form.accountId}
                              allowManual
                              className="flex-1"
                            />
                          ) : (
                            <input
                              type="text"
                              value={draftId}
                              onChange={(e) => setResourceIdDraft(resource.key, e.target.value)}
                              placeholder={`Enter ${resource.idLabel}`}
                              className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                            />
                          )}
                        <button
                          type="button"
                          onClick={() => addResourceId(resource.key)}
                          className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                        >
                          <Plus size={16} />
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mb-2">
                        Explicit IDs override discovery. Leave empty to rely on tags.
                      </p>
                      {ids.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {ids.map((id) => (
                              <span
                                key={id}
                                className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-sm text-gray-300"
                              >
                                {id}
                                <button
                                  type="button"
                                  onClick={() => removeResourceId(resource.key, id)}
                                  className="text-gray-500 hover:text-red-400"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      <div>
                      <label className="block text-sm font-medium text-gray-300 mb-2">
                        Tags
                      </label>
                        <div className="flex gap-2 mb-2">
                          <input
                            type="text"
                            value={draftTag.key}
                            onChange={(e) => setResourceTagDraft(resource.key, 'key', e.target.value)}
                            placeholder="Key"
                            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                          />
                          <input
                            type="text"
                            value={draftTag.value}
                            onChange={(e) => setResourceTagDraft(resource.key, 'value', e.target.value)}
                            placeholder="Value"
                            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
                            onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addResourceTag(resource.key))}
                          />
                        <button
                          type="button"
                          onClick={() => addResourceTag(resource.key)}
                          className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                        >
                          <Plus size={16} />
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 mb-2">
                        Tags are used if no ID is defined for this resource.
                      </p>
                      {Object.keys(tags).length > 0 && (
                        <div className="flex flex-wrap gap-2">
                            {Object.entries(tags).map(([key, value]) => (
                              <span
                                key={key}
                                className="inline-flex items-center gap-1 px-2 py-1 bg-gray-800 rounded text-sm text-gray-300"
                              >
                                {key}: {value}
                                <button
                                  type="button"
                                  onClick={() => removeResourceTag(resource.key, key)}
                                  className="text-gray-500 hover:text-red-400"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
              <Radar size={18} className="text-blue-400" />
              Run Discovery
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Save the environment, then discover infrastructure to suggest nodes.
            </p>
            <button
              type="button"
              onClick={runDiscovery}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-500"
              disabled={discoveryLoading}
            >
              <RefreshCw size={16} className={discoveryLoading ? 'animate-spin' : ''} />
              Save & Discover
            </button>
            {discoveryError && (
              <p className="text-sm text-red-400 mt-3">{discoveryError}</p>
            )}
            {discoveryData && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3 text-sm text-gray-300">
                {['cloudfront', 'alb', 'rds', 'redis', 'efs'].map((key) => {
                  const value = discoveryData[key];
                  const label = key === 'cloudfront'
                    ? value?.id || (value?.distributionCount ? `${value.distributionCount} distributions` : null)
                    : key === 'alb'
                      ? value?.name || value?.arn
                      : key === 'rds'
                        ? value?.identifier
                        : key === 'redis'
                          ? value?.clusterId
                          : key === 'efs'
                            ? value?.fileSystemId
                            : null;
                  return (
                    <div key={key} className="bg-gray-800 rounded-lg px-3 py-2">
                      <span className="capitalize">{key}</span>
                      <span className="float-right text-gray-400">
                        {label || (value ? 'found' : 'n/a')}
                      </span>
                    </div>
                  );
                })}
                <div className="bg-gray-800 rounded-lg px-3 py-2">
                  <span>S3 buckets</span>
                  <span className="float-right text-gray-400">
                    {discoveryData.s3Buckets?.length || 0}
                  </span>
                </div>
              </div>
            )}

            {(discoveredCloudfrontIds.length ||
              discoveredAlbIds.length ||
              discoveredRdsIds.length ||
              discoveredRedisIds.length ||
              discoveredEfsIds.length) > 0 && (
              <div className="mt-5 border-t border-gray-800 pt-4">
                <p className="text-xs text-gray-500 mb-3">Apply discovered IDs to config</p>
                <div className="flex flex-wrap gap-2">
                  {discoveredCloudfrontIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => addDiscoveredIds('cloudfront', discoveredCloudfrontIds)}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Use CloudFront ({discoveredCloudfrontIds.length})
                    </button>
                  )}
                  {discoveredAlbIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => addDiscoveredIds('alb', discoveredAlbIds)}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Use ALB
                    </button>
                  )}
                  {discoveredRdsIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => addDiscoveredIds('rds', discoveredRdsIds)}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Use RDS
                    </button>
                  )}
                  {discoveredRedisIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => addDiscoveredIds('redis', discoveredRedisIds)}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Use Redis
                    </button>
                  )}
                  {discoveredEfsIds.length > 0 && (
                    <button
                      type="button"
                      onClick={() => addDiscoveredIds('efs', discoveredEfsIds)}
                      className="px-3 py-1.5 text-xs rounded-md bg-gray-800 text-gray-200 hover:bg-gray-700"
                    >
                      Use EFS
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {wizardStep === 5 && (
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Review</h2>
            <div className="grid grid-cols-2 gap-4 text-sm text-gray-300">
              <div>
                <div className="text-gray-500">Environment</div>
                <div>{form.envId}</div>
              </div>
              <div>
                <div className="text-gray-500">Account</div>
                <div>{form.accountId || 'n/a'}</div>
              </div>
              <div>
                <div className="text-gray-500">Region</div>
                <div>{form.region}</div>
              </div>
              <div>
                <div className="text-gray-500">Cluster</div>
                <div>{form.clusterName || 'n/a'}</div>
              </div>
              <div>
                <div className="text-gray-500">Services</div>
                <div>{form.services.length}</div>
              </div>
              <div>
                <div className="text-gray-500">Default Tags</div>
                <div>{Object.keys(form.infrastructure.defaultTags || {}).length}</div>
              </div>
              <div>
                <div className="text-gray-500">Pipelines Configured</div>
                <div>
                  {Object.values(form.pipelines?.services || {}).filter(svc =>
                    svc.deploy?.enabled || svc.build?.enabled
                  ).length} services
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 text-xs text-gray-500">
        <Info size={14} className="text-gray-500" />
        Each step saves changes before moving on.
      </div>

      {renderStepActions()}
    </div>
  );
}
