/**
 * CIProviderForm - Create/Edit CI/CD Provider
 *
 * Form to configure CI/CD provider (Jenkins, ArgoCD, etc.)
 */
import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  GitBranch,
  Save,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  XCircle,
  Zap,
  Eye,
  EyeOff,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const PROVIDER_TYPES = [
  { value: 'jenkins', label: 'Jenkins', description: 'Jenkins CI/CD server' },
  { value: 'argocd', label: 'ArgoCD', description: 'GitOps continuous delivery' },
  { value: 'codepipeline', label: 'AWS CodePipeline', description: 'AWS native CI/CD' },
  { value: 'github-actions', label: 'GitHub Actions', description: 'GitHub CI/CD' },
  { value: 'azure-devops', label: 'Azure DevOps', description: 'Azure Pipelines' },
];

export default function CIProviderForm() {
  const { providerId } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(providerId) && providerId !== 'new';

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [showToken, setShowToken] = useState(false);

  const [form, setForm] = useState({
    providerId: '',
    type: 'jenkins',
    name: '',
    url: '',
    user: '',
    token: '',
  });

  // Load existing provider for edit
  useEffect(() => {
    if (isEdit) {
      loadProvider();
    }
  }, [providerId]);

  // Reset test result when form changes
  useEffect(() => {
    setTestResult(null);
  }, [form.url, form.user, form.token]);

  const loadProvider = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(`/api/config/ci-providers/${providerId}`);

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Provider not found');
        }
        throw new Error('Failed to load provider');
      }

      const data = await response.json();
      setForm({
        providerId: data.providerId || '',
        type: data.type || 'jenkins',
        name: data.name || '',
        url: data.url || '',
        user: data.user || '',
        token: '', // Never loaded from backend for security
      });
    } catch (err) {
      console.error('Error loading provider:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.providerId) {
      setError('Provider ID is required');
      return;
    }
    if (!form.type) {
      setError('Provider type is required');
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const method = isEdit ? 'PUT' : 'POST';
      const url = isEdit
        ? `/api/config/ci-providers/${providerId}`
        : '/api/config/ci-providers';

      const payload = { ...form };
      // Only send token if it was modified (not empty)
      if (!payload.token && isEdit) {
        delete payload.token;
      }

      const response = await fetchWithRetry(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save provider');
      }

      navigate('/admin/config/ci-providers');
    } catch (err) {
      console.error('Error saving provider:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (!form.url) {
      setError('URL is required to test connection');
      return;
    }

    // For Jenkins, user is required
    if (form.type === 'jenkins' && !form.user) {
      setError('Username is required to test Jenkins connection');
      return;
    }

    // For new providers or when token is provided, we need the token
    if (!isEdit && !form.token) {
      setError('Token is required to test connection');
      return;
    }

    setTesting(true);
    setTestResult(null);
    setError(null);

    try {
      let response;

      if (isEdit && !form.token) {
        // Existing provider without new token - test using saved credentials
        response = await fetchWithRetry(`/api/config/ci-providers/${providerId}/test`, {
          method: 'POST',
        });
      } else {
        // New provider or existing with new token - test with provided credentials
        response = await fetchWithRetry('/api/config/ci-providers/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            type: form.type,
            url: form.url,
            user: form.user,
            token: form.token,
          }),
        });
      }

      const data = await response.json();
      setTestResult(data);
    } catch (err) {
      console.error('Error testing provider:', err);
      setTestResult({ success: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleChange = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  // Auto-generate providerId from name if creating new
  const handleNameChange = (value) => {
    setForm((prev) => ({
      ...prev,
      name: value,
      // Only auto-generate providerId if it's empty or matches the previous auto-generated value
      providerId: isEdit ? prev.providerId : (
        !prev.providerId || prev.providerId === prev.name.toLowerCase().replace(/[^a-z0-9]+/g, '-')
          ? value.toLowerCase().replace(/[^a-z0-9]+/g, '-')
          : prev.providerId
      ),
    }));
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

  const selectedType = PROVIDER_TYPES.find((t) => t.value === form.type);
  const needsUser = ['jenkins'].includes(form.type);

  return (
    <div className="p-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-4 mb-6">
        <Link
          to="/admin/config/ci-providers"
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg"
        >
          <ArrowLeft size={20} />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold text-white">
            {isEdit ? 'Edit CI Provider' : 'New CI Provider'}
          </h1>
          <p className="text-gray-500">
            {isEdit ? `Editing ${providerId}` : 'Configure a new CI/CD provider'}
          </p>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 bg-red-900/20 border border-red-800 rounded-lg p-4 flex items-start gap-3">
          <AlertCircle size={20} className="text-red-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-red-400 font-medium">Error</p>
            <p className="text-gray-400 text-sm">{error}</p>
          </div>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <GitBranch size={18} className="text-green-400" />
            Provider Configuration
          </h2>

          {/* Type */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Provider Type
            </label>
            <select
              value={form.type}
              onChange={(e) => handleChange('type', e.target.value)}
              disabled={isEdit}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none disabled:opacity-50"
            >
              {PROVIDER_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </select>
            {selectedType && (
              <p className="text-xs text-gray-500 mt-1">{selectedType.description}</p>
            )}
          </div>

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Display Name
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g., Jenkins Rubix"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Provider ID */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Provider ID
            </label>
            <input
              type="text"
              value={form.providerId}
              onChange={(e) => handleChange('providerId', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-'))}
              placeholder="e.g., jenkins-rubix"
              disabled={isEdit}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none disabled:opacity-50"
            />
            <p className="text-xs text-gray-500 mt-1">
              Unique identifier used to reference this provider
            </p>
          </div>

          {/* URL */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              URL
            </label>
            <input
              type="url"
              value={form.url}
              onChange={(e) => handleChange('url', e.target.value)}
              placeholder={form.type === 'jenkins' ? 'https://jenkins.example.com' : 'https://argocd.example.com'}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* User (for Jenkins) */}
          {needsUser && (
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                Username
              </label>
              <input
                type="text"
                value={form.user}
                onChange={(e) => handleChange('user', e.target.value)}
                placeholder="jenkins-admin"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
            </div>
          )}

          {/* Token */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              {form.type === 'jenkins' ? 'API Token' : 'Bearer Token'}
              {isEdit && <span className="text-gray-600 ml-2">(leave empty to keep current)</span>}
            </label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={form.token}
                onChange={(e) => handleChange('token', e.target.value)}
                placeholder={isEdit ? '********' : 'Enter API token'}
                className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-gray-300"
              >
                {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Token will be stored securely in AWS Secrets Manager
            </p>
          </div>
        </div>

        {/* Test Connection */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium text-white">Test Connection</h3>
              <p className="text-xs text-gray-500">
                {isEdit && !form.token
                  ? 'Test with saved credentials'
                  : 'Verify the provider is accessible before saving'}
              </p>
            </div>
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || (!isEdit && !form.token)}
              className="flex items-center gap-2 px-3 py-2 text-sm bg-gray-800 hover:bg-gray-700 text-white rounded-lg disabled:opacity-50"
            >
              {testing ? (
                <RefreshCw size={14} className="animate-spin" />
              ) : (
                <Zap size={14} />
              )}
              Test
            </button>
          </div>

          {testResult && (
            <div className={`mt-4 p-3 rounded-lg ${testResult.success ? 'bg-green-900/20 border border-green-800' : 'bg-red-900/20 border border-red-800'}`}>
              <div className="flex items-start gap-2">
                {testResult.success ? (
                  <CheckCircle size={16} className="text-green-400 mt-0.5" />
                ) : (
                  <XCircle size={16} className="text-red-400 mt-0.5" />
                )}
                <div>
                  <p className={`text-sm font-medium ${testResult.success ? 'text-green-400' : 'text-red-400'}`}>
                    {testResult.success ? 'Connection successful' : 'Connection failed'}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    {testResult.message || testResult.error}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            {isEdit ? 'Save Changes' : 'Create Provider'}
          </button>
          <Link
            to="/admin/config/ci-providers"
            className="px-4 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
          >
            Cancel
          </Link>
        </div>
      </form>
    </div>
  );
}
