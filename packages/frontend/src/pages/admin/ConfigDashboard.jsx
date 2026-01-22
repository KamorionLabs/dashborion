/**
 * Config Dashboard - Admin Overview
 *
 * Shows summary statistics and quick links for config management.
 */
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FolderKanban,
  Server,
  Cloud,
  Layers,
  GitBranch,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { fetchWithRetry } from '../../utils/fetch';

export default function ConfigDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchStats = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch all data in parallel
      const [projectsRes, clustersRes, accountsRes, providersRes, settingsRes] = await Promise.all([
        fetchWithRetry('/api/config/projects'),
        fetchWithRetry('/api/config/clusters'),
        fetchWithRetry('/api/config/aws-accounts'),
        fetchWithRetry('/api/config/ci-providers'),
        fetchWithRetry('/api/config/settings'),
      ]);

      if (!projectsRes.ok || !clustersRes.ok || !accountsRes.ok) {
        throw new Error('Failed to fetch config data');
      }

      const projectsData = await projectsRes.json();
      const clustersData = await clustersRes.json();
      const accountsData = await accountsRes.json();
      const providersData = providersRes.ok ? await providersRes.json() : { ciProviders: [] };
      const settings = await settingsRes.json();

      const projects = projectsData.projects || [];
      const clusters = clustersData.clusters || [];
      const accounts = accountsData.awsAccounts || [];
      const ciProviders = providersData.ciProviders || [];

      // Count environments across all projects
      const envCount = projects.reduce((acc, p) => acc + (p.environmentCount || 0), 0);

      setStats({
        projects: projects.length,
        environments: envCount,
        clusters: clusters.length,
        accounts: accounts.length,
        ciProviders: ciProviders.length,
        features: settings?.features || {},
      });
    } catch (err) {
      console.error('Error fetching stats:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const navigate = useNavigate();

  const StatCard = ({ icon: Icon, label, value, linkTo, color = 'blue' }) => (
    <div
      onClick={() => linkTo && navigate(linkTo)}
      className={`bg-gray-900 border border-gray-800 rounded-lg p-6 ${linkTo ? 'cursor-pointer hover:border-gray-700 hover:bg-gray-900/80 transition-colors' : ''}`}
    >
      <div className="flex items-center justify-between">
        <div className={`p-3 rounded-lg bg-${color}-600/20`}>
          <Icon size={24} className={`text-${color}-400`} />
        </div>
        <span className="text-3xl font-bold text-white">{value}</span>
      </div>
      <h3 className="text-gray-400 mt-4">{label}</h3>
    </div>
  );

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
          <h2 className="text-lg font-semibold text-red-400">Error Loading Config</h2>
          <p className="text-gray-400 mt-2">{error}</p>
          <button
            onClick={fetchStats}
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
          <h1 className="text-2xl font-semibold text-white">Config Registry</h1>
          <p className="text-gray-500">Manage projects, environments, clusters, and AWS accounts</p>
        </div>
        <button
          onClick={fetchStats}
          className="flex items-center gap-2 px-3 py-2 text-sm text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg"
        >
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <StatCard
          icon={FolderKanban}
          label="Projects"
          value={stats?.projects || 0}
          linkTo="/admin/config/projects"
          color="blue"
        />
        <StatCard
          icon={Layers}
          label="Environments"
          value={stats?.environments || 0}
          color="green"
        />
        <StatCard
          icon={Cloud}
          label="AWS Accounts"
          value={stats?.accounts || 0}
          linkTo="/admin/config/accounts"
          color="orange"
        />
        <StatCard
          icon={Server}
          label="Clusters"
          value={stats?.clusters || 0}
          linkTo="/admin/config/clusters"
          color="purple"
        />
        <StatCard
          icon={GitBranch}
          label="CI Providers"
          value={stats?.ciProviders || 0}
          linkTo="/admin/config/ci-providers"
          color="cyan"
        />
      </div>

      {/* Quick Actions */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link
            to="/admin/config/projects/new"
            className="flex items-center gap-3 p-4 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <div className="p-2 bg-blue-600/20 rounded-lg">
              <FolderKanban size={20} className="text-blue-400" />
            </div>
            <div>
              <h3 className="text-white font-medium">New Project</h3>
              <p className="text-sm text-gray-500">Create a new project with environments</p>
            </div>
          </Link>

          <Link
            to="/admin/config/accounts/new"
            className="flex items-center gap-3 p-4 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <div className="p-2 bg-orange-600/20 rounded-lg">
              <Cloud size={20} className="text-orange-400" />
            </div>
            <div>
              <h3 className="text-white font-medium">Add AWS Account</h3>
              <p className="text-sm text-gray-500">Configure cross-account access</p>
            </div>
          </Link>

          <Link
            to="/admin/config/clusters/new"
            className="flex items-center gap-3 p-4 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <div className="p-2 bg-purple-600/20 rounded-lg">
              <Server size={20} className="text-purple-400" />
            </div>
            <div>
              <h3 className="text-white font-medium">Add Cluster</h3>
              <p className="text-sm text-gray-500">Register an EKS or ECS cluster</p>
            </div>
          </Link>

          <Link
            to="/admin/config/ci-providers/new"
            className="flex items-center gap-3 p-4 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
          >
            <div className="p-2 bg-cyan-600/20 rounded-lg">
              <GitBranch size={20} className="text-cyan-400" />
            </div>
            <div>
              <h3 className="text-white font-medium">Add CI Provider</h3>
              <p className="text-sm text-gray-500">Configure Jenkins, ArgoCD, etc.</p>
            </div>
          </Link>
        </div>
      </div>

      {/* Features Status */}
      {stats?.features && Object.keys(stats.features).length > 0 && (
        <div className="mt-6 bg-gray-900 border border-gray-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Enabled Features</h2>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.features).map(([feature, enabled]) => (
              <span
                key={feature}
                className={`px-3 py-1 rounded-full text-sm ${
                  enabled
                    ? 'bg-green-600/20 text-green-400'
                    : 'bg-gray-700 text-gray-500'
                }`}
              >
                {feature}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
