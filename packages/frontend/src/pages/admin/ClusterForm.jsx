/**
 * ClusterForm - Create/Edit Cluster
 *
 * Form to configure EKS/ECS cluster with AWS discovery.
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Server,
  Save,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  Search,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';
import ResourcePicker from '../../components/admin/ResourcePicker';

const AWS_REGIONS = [
  { value: 'eu-central-1', label: 'EU (Frankfurt)' },
  { value: 'eu-west-1', label: 'EU (Ireland)' },
  { value: 'eu-west-2', label: 'EU (London)' },
  { value: 'eu-west-3', label: 'EU (Paris)' },
  { value: 'us-east-1', label: 'US East (N. Virginia)' },
  { value: 'us-west-2', label: 'US West (Oregon)' },
  { value: 'ap-southeast-1', label: 'Asia Pacific (Singapore)' },
];

const CLUSTER_TYPES = [
  { value: 'eks', label: 'Amazon EKS' },
  { value: 'ecs', label: 'Amazon ECS' },
];

export default function ClusterForm() {
  const { clusterId } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(clusterId);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [awsAccounts, setAwsAccounts] = useState([]);

  const [form, setForm] = useState({
    clusterId: '',
    displayName: '',
    type: 'eks',
    awsAccountId: '',
    region: 'eu-central-1',
    clusterName: '', // Actual AWS cluster name (can differ from clusterId)
  });

  // Load AWS accounts for selection
  useEffect(() => {
    loadAwsAccounts();
  }, []);

  // Load existing cluster for edit
  useEffect(() => {
    if (isEdit) {
      loadCluster();
    }
  }, [clusterId]);

  const loadAwsAccounts = async () => {
    try {
      const response = await fetchWithRetry('/api/config/aws-accounts');
      if (response.ok) {
        const data = await response.json();
        setAwsAccounts(data.awsAccounts || []);
      }
    } catch (err) {
      console.error('Error loading AWS accounts:', err);
    }
  };

  const loadCluster = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(`/api/config/clusters/${clusterId}`);

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Cluster not found');
        }
        throw new Error('Failed to load cluster');
      }

      const data = await response.json();
      setForm({
        clusterId: data.clusterId || '',
        displayName: data.displayName || '',
        type: data.type || 'eks',
        awsAccountId: data.awsAccountId || '',
        region: data.region || 'eu-central-1',
        clusterName: data.clusterName || '',
      });
    } catch (err) {
      console.error('Error loading cluster:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.clusterId || !form.type || !form.awsAccountId) {
      setError('Cluster ID, Type, and AWS Account are required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const method = isEdit ? 'PUT' : 'POST';
      const url = isEdit
        ? `/api/config/clusters/${clusterId}`
        : '/api/config/clusters';

      const response = await fetchWithRetry(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save cluster');
      }

      navigate('/admin/config/clusters');
    } catch (err) {
      console.error('Error saving cluster:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Handle discovery selection
  const handleClusterSelect = (resource) => {
    if (resource) {
      setForm({
        ...form,
        clusterName: resource.name || resource.clusterName,
        // Auto-fill clusterId if empty
        clusterId: form.clusterId || resource.name || resource.clusterName,
      });
    }
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
    <div className="p-6 max-w-2xl">
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/admin/config/clusters"
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft size={16} />
          Back to Clusters
        </Link>
        <h1 className="text-2xl font-semibold text-white">
          {isEdit ? 'Edit Cluster' : 'Add Cluster'}
        </h1>
        <p className="text-gray-500">
          Configure cluster settings and discovery
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
        {/* Cluster Type */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Cluster Type <span className="text-red-400">*</span>
          </label>
          <div className="flex gap-2">
            {CLUSTER_TYPES.map((type) => (
              <button
                key={type.value}
                type="button"
                onClick={() => setForm({ ...form, type: type.value })}
                className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition-colors ${
                  form.type === type.value
                    ? 'border-blue-500 bg-blue-600/20 text-blue-400'
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600'
                }`}
              >
                {type.label}
              </button>
            ))}
          </div>
        </div>

        {/* AWS Account */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            AWS Account <span className="text-red-400">*</span>
          </label>
          <select
            value={form.awsAccountId}
            onChange={(e) => setForm({ ...form, awsAccountId: e.target.value })}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="">Select AWS Account...</option>
            {awsAccounts.map((account) => (
              <option key={account.accountId} value={account.accountId}>
                {account.displayName || account.accountId} ({account.accountId})
              </option>
            ))}
          </select>
          {awsAccounts.length === 0 && (
            <p className="mt-1 text-xs text-yellow-400">
              No AWS accounts configured.{' '}
              <Link to="/admin/config/accounts/new" className="underline">
                Add one first
              </Link>
            </p>
          )}
        </div>

        {/* Region */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Region <span className="text-red-400">*</span>
          </label>
          <select
            value={form.region}
            onChange={(e) => setForm({ ...form, region: e.target.value })}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
          >
            {AWS_REGIONS.map((region) => (
              <option key={region.value} value={region.value}>
                {region.label} ({region.value})
              </option>
            ))}
          </select>
        </div>

        {/* Cluster Name (with Discovery) */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Cluster Name
          </label>
          {form.awsAccountId ? (
            <ResourcePicker
              accountId={form.awsAccountId}
              region={form.region}
              resourceType={form.type}
              value={form.clusterName}
              onChange={handleClusterSelect}
              placeholder={`Discover ${form.type.toUpperCase()} clusters...`}
            />
          ) : (
            <input
              type="text"
              value={form.clusterName}
              onChange={(e) => setForm({ ...form, clusterName: e.target.value })}
              placeholder="k8s-dig-prd-webshop"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          )}
          <p className="mt-1 text-xs text-gray-500">
            The actual AWS cluster name. Select an AWS account to enable discovery.
          </p>
        </div>

        {/* Cluster ID */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Cluster ID <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={form.clusterId}
            onChange={(e) => setForm({ ...form, clusterId: e.target.value })}
            disabled={isEdit}
            placeholder="dig-prd-webshop"
            pattern="[a-z0-9-]+"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
          />
          <p className="mt-1 text-xs text-gray-500">
            Unique identifier for this cluster in Config Registry (auto-filled from discovery)
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
            placeholder="Production Webshop Cluster"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
          />
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
            {isEdit ? 'Save Changes' : 'Create Cluster'}
          </button>
          <Link
            to="/admin/config/clusters"
            className="px-4 py-2 text-gray-400 hover:text-white"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
