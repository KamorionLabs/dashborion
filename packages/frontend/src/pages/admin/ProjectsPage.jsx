/**
 * ProjectsPage - Projects Management
 *
 * List and manage projects with their environments.
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  FolderKanban,
  Plus,
  RefreshCw,
  AlertCircle,
  Trash2,
  Edit,
  Layers,
  ChevronRight,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

export default function ProjectsPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const fetchProjects = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry('/api/config/projects');

      if (!response.ok) {
        throw new Error('Failed to fetch projects');
      }

      const data = await response.json();
      setProjects(data.projects || []);
    } catch (err) {
      console.error('Error fetching projects:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
  }, []);

  const handleDelete = async (projectId) => {
    if (!confirm(`Delete project "${projectId}" and all its environments?`)) {
      return;
    }

    setDeleting(projectId);

    try {
      const response = await fetchWithRetry(`/api/config/projects/${projectId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete project');
      }

      setProjects(projects.filter((p) => p.projectId !== projectId));
    } catch (err) {
      console.error('Error deleting project:', err);
      alert(`Error: ${err.message}`);
    } finally {
      setDeleting(null);
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
          <h2 className="text-lg font-semibold text-red-400">Error Loading Projects</h2>
          <p className="text-gray-400 mt-2">{error}</p>
          <button
            onClick={fetchProjects}
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
          <h1 className="text-2xl font-semibold text-white">Projects</h1>
          <p className="text-gray-500">Manage projects and their environments</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchProjects}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
          <Link
            to="/admin/config/projects/new"
            className="flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Add Project
          </Link>
        </div>
      </div>

      {/* Projects List */}
      {projects.length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-12 text-center">
          <FolderKanban size={48} className="mx-auto text-gray-600 mb-4" />
          <h2 className="text-lg font-semibold text-white mb-2">No Projects</h2>
          <p className="text-gray-500 mb-4">
            Create your first project to get started.
          </p>
          <Link
            to="/admin/config/projects/new"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-lg"
          >
            <Plus size={16} />
            Create First Project
          </Link>
        </div>
      ) : (
        <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-850">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Project
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Environments
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Description
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {projects.map((project) => (
                <tr key={project.projectId} className="hover:bg-gray-850">
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-blue-600/20 rounded-lg">
                        <FolderKanban size={16} className="text-blue-400" />
                      </div>
                      <div>
                        <div className="text-sm font-medium text-white">
                          {project.displayName || project.projectId}
                        </div>
                        <div className="text-xs text-gray-500">{project.projectId}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    {project.orchestratorType ? (
                      <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                        project.orchestratorType === 'eks'
                          ? 'bg-purple-600/20 text-purple-400'
                          : 'bg-orange-600/20 text-orange-400'
                      }`}>
                        {project.orchestratorType.toUpperCase()}
                      </span>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="px-4 py-4">
                    <Link
                      to={`/admin/config/projects/${project.projectId}/environments`}
                      className="flex items-center gap-2 text-sm text-gray-400 hover:text-white"
                    >
                      <Layers size={14} />
                      <span>{project.environmentCount || 0} environments</span>
                      <ChevronRight size={14} />
                    </Link>
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-400">
                    {project.description || '-'}
                  </td>
                  <td className="px-4 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Link
                        to={`/admin/config/projects/${project.projectId}`}
                        className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded"
                      >
                        <Edit size={16} />
                      </Link>
                      <button
                        onClick={() => handleDelete(project.projectId)}
                        disabled={deleting === project.projectId}
                        className="p-2 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded disabled:opacity-50"
                      >
                        {deleting === project.projectId ? (
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
