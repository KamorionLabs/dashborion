/**
 * SettingsPage - Global Settings
 *
 * Configure global application settings, feature flags, and comparison groups.
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Settings,
  Save,
  ArrowLeft,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Key,
  Eye,
  EyeOff,
  Plug,
  Lock,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const AVAILABLE_FEATURES = [
  { key: 'comparison', label: 'Environment Comparison', description: 'Enable environment comparison features' },
  { key: 'discovery', label: 'AWS Discovery', description: 'Enable AWS resource discovery' },
  { key: 'pipelines', label: 'Pipeline Integration', description: 'Enable CI/CD pipeline integration (Jenkins, ArgoCD)' },
  { key: 'replication', label: 'EFS Replication', description: 'Enable EFS replication monitoring' },
];

const CI_PROVIDERS = [
  {
    key: 'jenkins-token',
    label: 'Jenkins',
    description: 'Jenkins API token for build pipelines',
    urlField: true,
    urlPlaceholder: 'https://jenkins.example.com',
    userField: true,
  },
  {
    key: 'argocd-token',
    label: 'ArgoCD',
    description: 'ArgoCD API token for deployment pipelines',
    urlField: true,
    urlPlaceholder: 'https://argocd.example.com',
    userField: false,
  },
  {
    key: 'github-token',
    label: 'GitHub',
    description: 'GitHub personal access token for GitHub Actions',
    urlField: false,
    userField: false,
  },
];

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  const [settings, setSettings] = useState({
    features: {},
    comparisonGroups: [],
    secretsPrefix: '/dashborion',
  });

  const [newGroup, setNewGroup] = useState({ name: '', sourceEnv: '', destEnv: '' });

  // CI Provider tokens state
  const [providerTokens, setProviderTokens] = useState({});
  const [providerUrls, setProviderUrls] = useState({});
  const [providerUsers, setProviderUsers] = useState({});
  const [showTokens, setShowTokens] = useState({});
  const [savingToken, setSavingToken] = useState({});
  const [testingConnection, setTestingConnection] = useState({});
  const [tokenStatus, setTokenStatus] = useState({});

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry('/api/config/settings');

      if (!response.ok) {
        throw new Error('Failed to load settings');
      }

      const data = await response.json();
      setSettings({
        features: data.features || {},
        comparisonGroups: data.comparisonGroups || [],
        secretsPrefix: data.secretsPrefix || '/dashborion',
      });

      // Load token status for each provider
      const statuses = {};
      for (const provider of CI_PROVIDERS) {
        try {
          const tokenResponse = await fetchWithRetry(`/api/config/secrets/${provider.key}`);
          if (tokenResponse.ok) {
            const tokenData = await tokenResponse.json();
            statuses[provider.key] = {
              exists: tokenData.exists,
              lastModified: tokenData.lastModified,
            };
          }
        } catch {
          // Token doesn't exist yet
          statuses[provider.key] = { exists: false };
        }
      }
      setTokenStatus(statuses);
    } catch (err) {
      console.error('Error loading settings:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const response = await fetchWithRetry('/api/config/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          features: settings.features,
          comparisonGroups: settings.comparisonGroups,
          secretsPrefix: settings.secretsPrefix,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save settings');
      }

      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      console.error('Error saving settings:', err);
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleFeature = (key) => {
    setSettings({
      ...settings,
      features: {
        ...settings.features,
        [key]: !settings.features[key],
      },
    });
  };

  const addComparisonGroup = () => {
    if (!newGroup.name || !newGroup.sourceEnv || !newGroup.destEnv) {
      return;
    }

    setSettings({
      ...settings,
      comparisonGroups: [
        ...settings.comparisonGroups,
        { ...newGroup },
      ],
    });
    setNewGroup({ name: '', sourceEnv: '', destEnv: '' });
  };

  const removeComparisonGroup = (index) => {
    setSettings({
      ...settings,
      comparisonGroups: settings.comparisonGroups.filter((_, i) => i !== index),
    });
  };

  // Save a provider token to Secrets Manager
  const saveProviderToken = async (providerKey) => {
    const token = providerTokens[providerKey];
    if (!token) {
      setError('Token value is required');
      return;
    }

    const provider = CI_PROVIDERS.find(p => p.key === providerKey);

    setSavingToken({ ...savingToken, [providerKey]: true });
    setError(null);

    try {
      const body = {
        value: token,
        description: `Dashborion ${providerKey} for CI/CD integration`,
      };

      // Include url and user if they are configured for this provider
      if (provider?.urlField && providerUrls[providerKey]) {
        body.url = providerUrls[providerKey];
      }
      if (provider?.userField && providerUsers[providerKey]) {
        body.user = providerUsers[providerKey];
      }

      const response = await fetchWithRetry(`/api/config/secrets/${providerKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || 'Failed to save token');
      }

      const data = await response.json();
      setTokenStatus({
        ...tokenStatus,
        [providerKey]: { exists: true, lastModified: new Date().toISOString() },
      });
      setProviderTokens({ ...providerTokens, [providerKey]: '' }); // Clear input
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      console.error('Error saving token:', err);
      setError(err.message);
    } finally {
      setSavingToken({ ...savingToken, [providerKey]: false });
    }
  };

  // Test connection to a provider
  const testConnection = async (providerKey) => {
    const provider = CI_PROVIDERS.find(p => p.key === providerKey);
    if (!provider) return;

    setTestingConnection({ ...testingConnection, [providerKey]: true });
    setError(null);

    try {
      const body = {
        provider: providerKey.replace('-token', ''),
      };

      if (provider.urlField && providerUrls[providerKey]) {
        body.url = providerUrls[providerKey];
      }
      if (provider.userField && providerUsers[providerKey]) {
        body.user = providerUsers[providerKey];
      }
      // Send token from form if available (allows testing before save)
      if (providerTokens[providerKey]) {
        body.token = providerTokens[providerKey];
      }

      const response = await fetchWithRetry('/api/config/secrets/test-connection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.message || data.error || 'Connection test failed');
      }

      setTokenStatus({
        ...tokenStatus,
        [providerKey]: {
          ...tokenStatus[providerKey],
          connectionOk: true,
          connectionMessage: data.message,
        },
      });
    } catch (err) {
      console.error('Connection test failed:', err);
      setTokenStatus({
        ...tokenStatus,
        [providerKey]: {
          ...tokenStatus[providerKey],
          connectionOk: false,
          connectionMessage: err.message,
        },
      });
    } finally {
      setTestingConnection({ ...testingConnection, [providerKey]: false });
    }
  };

  const toggleShowToken = (providerKey) => {
    setShowTokens({ ...showTokens, [providerKey]: !showTokens[providerKey] });
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
    <div className="p-6 max-w-3xl">
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/admin/config"
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft size={16} />
          Back to Config
        </Link>
        <h1 className="text-2xl font-semibold text-white">Global Settings</h1>
        <p className="text-gray-500">
          Configure application-wide settings and feature flags
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 bg-red-900/20 border border-red-800 rounded-lg flex items-center gap-3">
          <AlertCircle size={20} className="text-red-400" />
          <span className="text-red-400">{error}</span>
        </div>
      )}

      {/* Success */}
      {success && (
        <div className="mb-6 p-4 bg-green-900/20 border border-green-800 rounded-lg flex items-center gap-3">
          <CheckCircle size={20} className="text-green-400" />
          <span className="text-green-400">Settings saved successfully</span>
        </div>
      )}

      <div className="space-y-8">
        {/* Secrets Configuration */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Lock size={20} className="text-yellow-500" />
            <h2 className="text-lg font-semibold text-white">Secrets Configuration</h2>
          </div>
          <p className="text-sm text-gray-500 mb-4">
            Configure the naming convention for secrets stored in AWS Secrets Manager.
          </p>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Secrets Prefix
              </label>
              <input
                type="text"
                value={settings.secretsPrefix}
                onChange={(e) => setSettings({ ...settings, secretsPrefix: e.target.value })}
                placeholder="/dashborion"
                className="w-full max-w-md px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
              />
              <p className="mt-1 text-xs text-gray-500">
                Secrets will be stored as: <code className="text-gray-400">{settings.secretsPrefix}/[project/]&lt;type&gt;</code>
              </p>
            </div>
          </div>
        </div>

        {/* CI/CD Provider Tokens */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center gap-2 mb-4">
            <Key size={20} className="text-blue-500" />
            <h2 className="text-lg font-semibold text-white">CI/CD Provider Tokens</h2>
          </div>
          <p className="text-sm text-gray-500 mb-4">
            Configure API tokens for CI/CD providers. Tokens are securely stored in AWS Secrets Manager.
          </p>
          <div className="space-y-6">
            {CI_PROVIDERS.map((provider) => (
              <div key={provider.key} className="p-4 bg-gray-800 rounded-lg">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-medium text-white">{provider.label}</h3>
                    <p className="text-xs text-gray-500">{provider.description}</p>
                  </div>
                  {tokenStatus[provider.key]?.exists && (
                    <span className="flex items-center gap-1 text-xs text-green-400">
                      <CheckCircle size={14} />
                      Configured
                    </span>
                  )}
                </div>

                <div className="space-y-3">
                  {/* URL field if needed */}
                  {provider.urlField && (
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">URL</label>
                      <input
                        type="text"
                        value={providerUrls[provider.key] || ''}
                        onChange={(e) => setProviderUrls({ ...providerUrls, [provider.key]: e.target.value })}
                        placeholder={provider.urlPlaceholder}
                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                  )}

                  {/* User field if needed */}
                  {provider.userField && (
                    <div>
                      <label className="block text-xs text-gray-500 mb-1">Username</label>
                      <input
                        type="text"
                        value={providerUsers[provider.key] || ''}
                        onChange={(e) => setProviderUsers({ ...providerUsers, [provider.key]: e.target.value })}
                        placeholder="jenkins-user"
                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
                      />
                    </div>
                  )}

                  {/* Token input */}
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">
                      {tokenStatus[provider.key]?.exists ? 'New Token (leave empty to keep existing)' : 'API Token'}
                    </label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <input
                          type={showTokens[provider.key] ? 'text' : 'password'}
                          value={providerTokens[provider.key] || ''}
                          onChange={(e) => setProviderTokens({ ...providerTokens, [provider.key]: e.target.value })}
                          placeholder="Enter API token..."
                          className="w-full px-3 py-2 pr-10 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
                        />
                        <button
                          type="button"
                          onClick={() => toggleShowToken(provider.key)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                        >
                          {showTokens[provider.key] ? <EyeOff size={16} /> : <Eye size={16} />}
                        </button>
                      </div>
                      <button
                        onClick={() => saveProviderToken(provider.key)}
                        disabled={!providerTokens[provider.key] || savingToken[provider.key]}
                        className="flex items-center gap-1 px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {savingToken[provider.key] ? (
                          <RefreshCw size={14} className="animate-spin" />
                        ) : (
                          <Save size={14} />
                        )}
                        Save
                      </button>
                    </div>
                  </div>

                  {/* Test connection button - show when token exists OR form has token + required fields */}
                  {(tokenStatus[provider.key]?.exists || (
                    providerTokens[provider.key] &&
                    (!provider.urlField || providerUrls[provider.key]) &&
                    (!provider.userField || providerUsers[provider.key])
                  )) && (
                    <div className="flex items-center gap-3 pt-2">
                      <button
                        onClick={() => testConnection(provider.key)}
                        disabled={testingConnection[provider.key]}
                        className="flex items-center gap-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded text-sm disabled:opacity-50"
                      >
                        {testingConnection[provider.key] ? (
                          <RefreshCw size={14} className="animate-spin" />
                        ) : (
                          <Plug size={14} />
                        )}
                        Test Connection
                      </button>
                      {tokenStatus[provider.key]?.connectionOk !== undefined && (
                        <span className={`text-xs ${tokenStatus[provider.key].connectionOk ? 'text-green-400' : 'text-red-400'}`}>
                          {tokenStatus[provider.key].connectionMessage}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Feature Flags */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Feature Flags</h2>
          <div className="space-y-4">
            {AVAILABLE_FEATURES.map((feature) => (
              <div
                key={feature.key}
                className="flex items-center justify-between p-3 bg-gray-800 rounded-lg"
              >
                <div>
                  <div className="text-sm font-medium text-white">{feature.label}</div>
                  <div className="text-xs text-gray-500">{feature.description}</div>
                </div>
                <button
                  type="button"
                  onClick={() => toggleFeature(feature.key)}
                  className="text-gray-400 hover:text-white"
                >
                  {settings.features[feature.key] ? (
                    <ToggleRight size={28} className="text-green-400" />
                  ) : (
                    <ToggleLeft size={28} />
                  )}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Comparison Groups */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Comparison Groups</h2>
          <p className="text-sm text-gray-500 mb-4">
            Define environment pairs for comparison (e.g., legacy-stg vs nh-stg)
          </p>

          {/* Existing Groups */}
          {settings.comparisonGroups.length > 0 && (
            <div className="space-y-2 mb-4">
              {settings.comparisonGroups.map((group, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 bg-gray-800 rounded-lg"
                >
                  <div className="flex items-center gap-4">
                    <span className="text-sm font-medium text-white">{group.name}</span>
                    <span className="text-xs text-gray-500">
                      {group.sourceEnv} → {group.destEnv}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeComparisonGroup(index)}
                    className="p-1 text-gray-400 hover:text-red-400"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add New Group */}
          <div className="flex items-end gap-2">
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">Group Name</label>
              <input
                type="text"
                value={newGroup.name}
                onChange={(e) => setNewGroup({ ...newGroup, name: e.target.value })}
                placeholder="stg-comparison"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">Source Env</label>
              <input
                type="text"
                value={newGroup.sourceEnv}
                onChange={(e) => setNewGroup({ ...newGroup, sourceEnv: e.target.value })}
                placeholder="legacy-stg"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-gray-500 mb-1">Dest Env</label>
              <input
                type="text"
                value={newGroup.destEnv}
                onChange={(e) => setNewGroup({ ...newGroup, destEnv: e.target.value })}
                placeholder="nh-stg"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <button
              type="button"
              onClick={addComparisonGroup}
              disabled={!newGroup.name || !newGroup.sourceEnv || !newGroup.destEnv}
              className="flex items-center gap-1 px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg text-sm disabled:opacity-50"
            >
              <Plus size={16} />
              Add
            </button>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex items-center gap-3 pt-4 border-t border-gray-800">
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
          >
            {saving ? (
              <RefreshCw size={16} className="animate-spin" />
            ) : (
              <Save size={16} />
            )}
            Save Settings
          </button>
          <button
            onClick={loadSettings}
            className="px-4 py-2 text-gray-400 hover:text-white"
          >
            Reset
          </button>
        </div>
      </div>
    </div>
  );
}
