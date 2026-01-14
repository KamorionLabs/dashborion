/**
 * EnvironmentsPage - Environments Management for a Project
 *
 * List and manage environments within a specific project.
 */
import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Layers,
  Plus,
  RefreshCw,
  AlertCircle,
  Trash2,
  Edit,
  ArrowLeft,
  CheckCircle,
  Clock,
  XCircle,
  Server,
  Globe,
  Tag,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

const STATUS_CONFIG = {
  active: { icon: CheckCircle, color: 'text-green-400', bg: 'bg-green-600/20', label: 'Active' },
  planned: { icon: Clock, color: 'text-yellow-400', bg: 'bg-yellow-600/20', label: 'Planned' },
  deprecated: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-600/20', label: 'Deprecated' },
};

export default function EnvironmentsPage() {
  const { projectId } = useParams();
  const [project, setProject] = useState(null);
  const [environments, setEnvironments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch project and environments in parallel
      const [projectRes, envsRes] = await Promise.all([
        fetchWithRetry(`/api/config/projects/${projectId}`),
        fetchWithRetry(`/api/config/projects/${projectId}/environments`),
      ]);

      if (!projectRes.ok) {
        throw new Error('Project not found');
      }

      const projectData = await projectRes.json();
      setProject(projectData);

      if (envsRes.ok) {
        const envsData = await envsRes.json();
        setEnvironments(envsData.environments || []);
      }
    } catch (err) {
      console.error('Error fetching data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [projectId]);

  const handleDelete = async (envId) => {
    if (!confirm(`Delete environment "${envId}"? This cannot be undone.`)) {
      return;
    }

    setDeleting(envId);

    try {
      const response = await fetchWithRetry(
        `/api/config/projects/${projectId}/environments/${envId}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        throw new Error('Failed to delete environment');
      }

      setEnvironments(environments.filter((e) => e.envId !== envId));
    } catch (err) {
      console.error('Error deleting environment:', err);
      alert(`Error: ${err.message}`);
    } finally {
      setDeleting(null);
    }
  };

  const StatusBadge = ({ status }) => {
    const config = STATUS_CONFIG[status] || STATUS_CONFIG.planned;
    const Icon = config.icon;
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${config.bg} ${config.color}`}>
        <Icon size={12} />
        {config.label}
      </span>
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

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6 text-center">
          <AlertCircle size={48} className="mx-auto text-red-400 mb-4" />
          <h2 className="text-lg font-semibold text-red-400">Error</h2>
          <p className="text-gray-400 mt-2">{error}</p>
          <button
            onClick={fetchData}
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
      <div className="mb-6">
        <Link
          to="/admin/config/projects"
          className="flex items-center gap-1 text-sm text-gray-400 hover:text-white mb-4"
        >
          <ArrowLeft size={16} />
          Back to Projects
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-white">
              {project?.displayName || projectId} - Environments
            </h1>
            <p className="text-gray-500">
              Manage environments for this project
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchData}
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
            >
              <RefreshCw size={16} />
              Refresh
            </button>
            <Link
              to={`/admin/config/projects/${projectId}`}
              className="flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
            >
              <Edit size={16} />
              Edit Project
            </Link>
            <Link
              to={`/admin/config/projects/${projectId}/environments/new`}
              className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
            >
              <Plus size={16} />
              Add Environment
            </Link>
          </div>
        </div>
      </div>

      {/* Environments List */}
      {environments.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-12 text-center">
          <Layers size={48} className="mx-auto text-gray-600 mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">No Environments</h2>
          <p className="text-gray-500 mb-4">
            Create your first environment for this project.
          </p>
          <Link
            to={`/admin/config/projects/${projectId}/environments/new`}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Create First Environment
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {environments.map((env) => (
            <div
              key={env.envId}
              className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-colors"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-4">
                  <div className="p-3 bg-green-600/20 rounded-lg">
                    <Layers size={20} className="text-green-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-3">
                      <h3 className="text-lg font-medium text-white">
                        {env.displayName || env.envId}
                      </h3>
                      <StatusBadge status={env.status} />
                    </div>
                    <p className="text-sm text-gray-500 mt-1">{env.envId}</p>

                    {/* Quick info - flat format */}
                    <div className="flex items-center gap-4 mt-3 text-sm text-gray-400">
                      {env.accountId && (
                        <span className="flex items-center gap-1">
                          <Globe size={14} />
                          {env.accountId} / {env.region || 'eu-central-1'}
                        </span>
                      )}
                      {env.clusterName && (
                        <span className="flex items-center gap-1">
                          <Server size={14} />
                          {env.clusterName}
                          {env.namespace && ` / ${env.namespace}`}
                        </span>
                      )}
                      {env.services?.length > 0 && (
                        <span className="flex items-center gap-1">
                          <Server size={14} />
                          {env.services.length} services
                        </span>
                      )}
                      {(() => {
                        const resourcesCount = Object.keys(env.infrastructure?.resources || {}).length;
                        const tagsCount = Object.keys(env.infrastructure?.defaultTags || {}).length;
                        return (
                          <>
                            {resourcesCount > 0 && (
                              <span className="flex items-center gap-1">
                                <Layers size={14} />
                                {resourcesCount} resources
                              </span>
                            )}
                            {tagsCount > 0 && (
                              <span className="flex items-center gap-1">
                                <Tag size={14} />
                                {tagsCount} tags
                              </span>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Link
                    to={`/admin/config/projects/${projectId}/environments/${env.envId}`}
                    className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                  >
                    <Edit size={16} />
                  </Link>
                  <button
                    onClick={() => handleDelete(env.envId)}
                    disabled={deleting === env.envId}
                    className="p-2 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded disabled:opacity-50"
                  >
                    {deleting === env.envId ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <Trash2 size={16} />
                    )}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
