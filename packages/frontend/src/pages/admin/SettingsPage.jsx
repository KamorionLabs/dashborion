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
  Lock,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const AVAILABLE_FEATURES = [
  { key: 'comparison', label: 'Environment Comparison', description: 'Enable environment comparison features' },
  { key: 'discovery', label: 'AWS Discovery', description: 'Enable AWS resource discovery' },
  { key: 'pipelines', label: 'Pipeline Integration', description: 'Enable CI/CD pipeline integration (Jenkins, ArgoCD)' },
  { key: 'replication', label: 'EFS Replication', description: 'Enable EFS replication monitoring' },
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
