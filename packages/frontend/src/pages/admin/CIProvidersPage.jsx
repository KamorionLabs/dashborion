/**
 * CIProvidersPage - CI/CD Providers Management
 *
 * List and manage CI/CD providers (Jenkins, ArgoCD, etc.)
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  GitBranch,
  Plus,
  RefreshCw,
  AlertCircle,
  Trash2,
  Edit,
  CheckCircle,
  XCircle,
  Zap,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const PROVIDER_ICONS = {
  jenkins: 'J',
  argocd: 'A',
  codepipeline: 'C',
  'github-actions': 'G',
  'azure-devops': 'D',
};

const PROVIDER_COLORS = {
  jenkins: 'bg-red-600/20 text-red-400',
  argocd: 'bg-orange-600/20 text-orange-400',
  codepipeline: 'bg-blue-600/20 text-blue-400',
  'github-actions': 'bg-gray-600/20 text-gray-400',
  'azure-devops': 'bg-cyan-600/20 text-cyan-400',
};

export default function CIProvidersPage() {
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [testing, setTesting] = useState(null);
  const [testResults, setTestResults] = useState({});

  const fetchProviders = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry('/api/config/ci-providers');

      if (!response.ok) {
        throw new Error('Failed to fetch providers');
      }

      const data = await response.json();
      setProviders(data.ciProviders || []);
    } catch (err) {
      console.error('Error fetching providers:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const handleDelete = async (providerId) => {
    if (!confirm(`Delete CI provider "${providerId}"? This will also delete the stored credentials.`)) {
      return;
    }

    setDeleting(providerId);

    try {
      const response = await fetchWithRetry(`/api/config/ci-providers/${providerId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete provider');
      }

      setProviders(providers.filter((p) => p.providerId !== providerId));
      setTestResults((prev) => {
        const next = { ...prev };
        delete next[providerId];
        return next;
      });
    } catch (err) {
      console.error('Error deleting provider:', err);
      alert(`Error: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  const handleTest = async (providerId) => {
    setTesting(providerId);
    setTestResults((prev) => ({ ...prev, [providerId]: null }));

    try {
      const response = await fetchWithRetry(`/api/config/ci-providers/${providerId}/test`, {
        method: 'POST',
      });

      const data = await response.json();
      setTestResults((prev) => ({ ...prev, [providerId]: data }));
    } catch (err) {
      console.error('Error testing provider:', err);
      setTestResults((prev) => ({
        ...prev,
        [providerId]: { success: false, error: err.message },
      }));
    } finally {
      setTesting(null);
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

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6 text-center">
          <AlertCircle size={48} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-lg font-semibold text-red-400">Error Loading Providers</h2>
          <p className="text-gray-400 mt-2">{error}</p>
          <button
            onClick={fetchProviders}
            className="mt-4 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">CI/CD Providers</h1>
          <p className="text-gray-500">Manage Jenkins, ArgoCD, and other CI/CD providers</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchProviders}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <Link
            to="/admin/config/ci-providers/new"
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add Provider
          </Link>
        </div>
      </div>

      {/* Providers List */}
      {providers.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-12 text-center">
          <GitBranch size={48} className="mx-auto text-gray-600 mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">No CI/CD Providers</h2>
          <p className="text-gray-500 mb-4">
            Add a provider to enable pipeline discovery and status tracking.
          </p>
          <Link
            to="/admin/config/ci-providers/new"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add First Provider
          </Link>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-850">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Provider
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  URL
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {providers.map((provider) => {
                const testResult = testResults[provider.providerId];
                return (
                  <tr key={provider.providerId} className="hover:bg-gray-850">
                    <td className="px-4 py-4">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${PROVIDER_COLORS[provider.type] || 'bg-gray-600/20 text-gray-400'}`}>
                          <span className="font-bold text-sm">
                            {PROVIDER_ICONS[provider.type] || '?'}
                          </span>
                        </div>
                        <div>
                          <div className="text-sm font-medium text-white">
                            {provider.name || provider.providerId}
                          </div>
                          <div className="text-xs text-gray-500">{provider.providerId}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-sm text-gray-400 capitalize">
                      {provider.type}
                    </td>
                    <td className="px-4 py-4">
                      {provider.url ? (
                        <a
                          href={provider.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-blue-400 hover:text-blue-300 truncate max-w-48 block"
                        >
                          {provider.url}
                        </a>
                      ) : (
                        <span className="text-xs text-gray-600">Not configured</span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      {testing === provider.providerId ? (
                        <div className="flex items-center gap-1">
                          <RefreshCw size={14} className="text-blue-400 animate-spin" />
                          <span className="text-xs text-gray-500">Testing...</span>
                        </div>
                      ) : testResult ? (
                        testResult.success ? (
                          <div className="flex items-center gap-1">
                            <CheckCircle size={14} className="text-green-400" />
                            <span className="text-xs text-green-400">Connected</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1">
                            <XCircle size={14} className="text-red-400" />
                            <span className="text-xs text-red-400" title={testResult.error}>
                              Failed
                            </span>
                          </div>
                        )
                      ) : provider.tokenSecret ? (
                        <div className="flex items-center gap-1">
                          <CheckCircle size={14} className="text-gray-500" />
                          <span className="text-xs text-gray-500">Configured</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <XCircle size={14} className="text-yellow-500" />
                          <span className="text-xs text-yellow-500">No credentials</span>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => handleTest(provider.providerId)}
                          disabled={testing === provider.providerId}
                          className="p-2 text-gray-400 hover:text-blue-400 hover:bg-gray-700 rounded disabled:opacity-50"
                          title="Test connection"
                        >
                          <Zap size={16} />
                        </button>
                        <Link
                          to={`/admin/config/ci-providers/${provider.providerId}`}
                          className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                        >
                          <Edit size={16} />
                        </Link>
                        <button
                          onClick={() => handleDelete(provider.providerId)}
                          disabled={deleting === provider.providerId}
                          className="p-2 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded disabled:opacity-50"
                        >
                          {deleting === provider.providerId ? (
                            <RefreshCw size={16} className="animate-spin" />
                          ) : (
                            <Trash2 size={16} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
