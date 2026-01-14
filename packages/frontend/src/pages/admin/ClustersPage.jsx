/**
 * ClustersPage - Clusters Management
 *
 * List and manage EKS/ECS clusters for orchestration.
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Server,
  Plus,
  RefreshCw,
  AlertCircle,
  Trash2,
  Edit,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

export default function ClustersPage() {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const fetchClusters = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry('/api/config/clusters');

      if (!response.ok) {
        throw new Error('Failed to fetch clusters');
      }

      const data = await response.json();
      setClusters(data.clusters || []);
    } catch (err) {
      console.error('Error fetching clusters:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClusters();
  }, []);

  const handleDelete = async (clusterId) => {
    if (!confirm(`Delete cluster "${clusterId}"?`)) {
      return;
    }

    setDeleting(clusterId);

    try {
      const response = await fetchWithRetry(`/api/config/clusters/${clusterId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete cluster');
      }

      setClusters(clusters.filter((c) => c.clusterId !== clusterId));
    } catch (err) {
      console.error('Error deleting cluster:', err);
      alert(`Error: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  const getClusterTypeColor = (type) => {
    switch (type) {
      case 'eks':
        return 'text-orange-400 bg-orange-600/20';
      case 'ecs':
        return 'text-blue-400 bg-blue-600/20';
      default:
        return 'text-gray-400 bg-gray-600/20';
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
          <h2 className="text-lg font-semibold text-red-400">Error Loading Clusters</h2>
          <p className="text-gray-400 mt-2">{error}</p>
          <button
            onClick={fetchClusters}
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
          <h1 className="text-2xl font-semibold text-white">Clusters</h1>
          <p className="text-gray-500">Manage EKS and ECS clusters</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchClusters}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <Link
            to="/admin/config/clusters/new"
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add Cluster
          </Link>
        </div>
      </div>

      {/* Clusters List */}
      {clusters.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-12 text-center">
          <Server size={48} className="mx-auto text-gray-600 mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">No Clusters</h2>
          <p className="text-gray-500 mb-4">
            Register an EKS or ECS cluster to get started.
          </p>
          <Link
            to="/admin/config/clusters/new"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add First Cluster
          </Link>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-850">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Cluster
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Region
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  AWS Account
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {clusters.map((cluster) => (
                <tr key={cluster.clusterId} className="hover:bg-gray-850">
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-purple-600/20 rounded-lg">
                        <Server size={16} className="text-purple-400" />
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white">
                          {cluster.displayName || cluster.clusterId}
                        </div>
                        <div className="text-xs text-gray-500">{cluster.clusterId}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium uppercase ${getClusterTypeColor(
                        cluster.type
                      )}`}
                    >
                      {cluster.type || 'unknown'}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-400">
                    {cluster.region || '-'}
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-400">
                    {cluster.awsAccountId || '-'}
                  </td>
                  <td className="px-4 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        to={`/admin/config/clusters/${cluster.clusterId}`}
                        className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                      >
                        <Edit size={16} />
                      </Link>
                      <button
                        onClick={() => handleDelete(cluster.clusterId)}
                        disabled={deleting === cluster.clusterId}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded disabled:opacity-50"
                      >
                        {deleting === cluster.clusterId ? (
                          <RefreshCw size={16} className="animate-spin" />
                        ) : (
                          <Trash2 size={16} />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
