/**
 * Service Detail Page - AWS ECS Plugin
 */

import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, RefreshCw, Server, Clock, Activity, FileText, Box,
  CheckCircle, XCircle, PlayCircle, StopCircle, RotateCcw
} from 'lucide-react';
import { fetchWithRetry } from '../../../../utils';

export default function ServiceDetailPage({ params, config }) {
  const navigate = useNavigate();
  const { project, env, service: serviceName } = params;

  const [service, setService] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');

  // Fetch service details
  const fetchServiceDetails = useCallback(async () => {
    if (!project || !env || !serviceName) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(`/api/${project}/services/${env}/${serviceName}`);
      if (response.ok) {
        const data = await response.json();
        setService(data.service);
        setTasks(data.tasks || []);
        setEvents(data.events || []);
      } else {
        throw new Error(`Failed to fetch service: ${response.status}`);
      }
    } catch (err) {
      console.error('Error fetching service details:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [project, env, serviceName]);

  useEffect(() => {
    fetchServiceDetails();
  }, [fetchServiceDetails]);

  // Handle actions
  const handleRestart = async () => {
    if (!confirm(`Are you sure you want to restart ${serviceName}?`)) return;

    try {
      const response = await fetchWithRetry(`/api/${project}/services/${env}/${serviceName}/restart`, {
        method: 'POST',
      });
      if (response.ok) {
        fetchServiceDetails();
      }
    } catch (err) {
      console.error('Error restarting service:', err);
    }
  };

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Server },
    { id: 'tasks', label: 'Tasks', icon: Box },
    { id: 'events', label: 'Events', icon: Activity },
    { id: 'logs', label: 'Logs', icon: FileText },
  ];

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(`/${project}/${env}/services`)}
            className="p-2 hover:bg-gray-800 rounded-lg"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-semibold text-white">{serviceName}</h1>
            <p className="text-gray-500 mt-1">{project} / {env}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleRestart}
            className="flex items-center gap-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-700 rounded-lg text-sm"
          >
            <RotateCcw size={16} />
            Restart
          </button>
          <button
            onClick={fetchServiceDetails}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800 mb-6">
        <nav className="flex gap-4">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-500 text-blue-400'
                  : 'border-transparent text-gray-400 hover:text-white'
              }`}
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <RefreshCw size={24} className="animate-spin text-blue-400" />
        </div>
      )}

      {error && (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {!loading && service && (
        <>
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm text-gray-500 mb-1">Status</h3>
                <p className="text-lg font-medium flex items-center gap-2">
                  {service.status === 'ACTIVE' ? (
                    <><CheckCircle size={18} className="text-green-400" /> Active</>
                  ) : (
                    <><XCircle size={18} className="text-red-400" /> {service.status}</>
                  )}
                </p>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm text-gray-500 mb-1">Tasks</h3>
                <p className="text-lg font-medium">
                  {service.runningCount} / {service.desiredCount}
                </p>
              </div>
              <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                <h3 className="text-sm text-gray-500 mb-1">Cluster</h3>
                <p className="text-lg font-medium truncate">
                  {service.clusterArn?.split('/').pop()}
                </p>
              </div>
            </div>
          )}

          {activeTab === 'tasks' && (
            <div className="space-y-2">
              {tasks.length === 0 ? (
                <p className="text-gray-500">No running tasks</p>
              ) : (
                tasks.map((task) => (
                  <div key={task.taskArn} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-sm">{task.taskArn?.split('/').pop()}</span>
                      <span className={`text-sm ${
                        task.lastStatus === 'RUNNING' ? 'text-green-400' : 'text-yellow-400'
                      }`}>
                        {task.lastStatus}
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'events' && (
            <div className="space-y-2">
              {events.length === 0 ? (
                <p className="text-gray-500">No recent events</p>
              ) : (
                events.slice(0, 20).map((event, i) => (
                  <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-3">
                    <p className="text-sm text-gray-300">{event.message}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      {new Date(event.createdAt).toLocaleString()}
                    </p>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === 'logs' && (
            <div className="text-center py-12">
              <FileText size={48} className="mx-auto text-gray-600 mb-4" />
              <p className="text-gray-500">
                <Link
                  to={`/${project}/${env}/services/${serviceName}/logs`}
                  className="text-blue-400 hover:underline"
                >
                  Open full logs viewer
                </Link>
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
