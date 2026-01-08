/**
 * Services Page - AWS ECS Plugin
 *
 * Lists all ECS services for the current project/environment.
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { RefreshCw, Server, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react';
import { fetchWithRetry } from '../../../../utils';

/**
 * Service status badge
 */
function StatusBadge({ status, runningCount, desiredCount }) {
  const isHealthy = status === 'ACTIVE' && runningCount === desiredCount;
  const isPending = runningCount < desiredCount;
  const isFailed = status !== 'ACTIVE';

  if (isFailed) {
    return (
      <span className="flex items-center gap-1 text-red-400">
        <XCircle size={14} />
        Failed
      </span>
    );
  }

  if (isPending) {
    return (
      <span className="flex items-center gap-1 text-yellow-400">
        <Clock size={14} />
        Pending ({runningCount}/{desiredCount})
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1 text-green-400">
      <CheckCircle size={14} />
      Running ({runningCount}/{desiredCount})
    </span>
  );
}

/**
 * Service card
 */
function ServiceCard({ service, onClick }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-colors"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gray-800 rounded-lg">
            <Server size={20} className="text-blue-400" />
          </div>
          <div>
            <h3 className="font-medium text-white">{service.serviceName}</h3>
            <p className="text-sm text-gray-500">{service.clusterArn?.split('/').pop()}</p>
          </div>
        </div>
        <StatusBadge
          status={service.status}
          runningCount={service.runningCount}
          desiredCount={service.desiredCount}
        />
      </div>

      {/* Deployment info */}
      {service.deployments?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <p className="text-xs text-gray-500">
            Last deployment: {new Date(service.deployments[0].createdAt).toLocaleString()}
          </p>
        </div>
      )}
    </button>
  );
}

/**
 * Services Page component
 */
export default function ServicesPage({ params, config }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { project, env } = params;

  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Fetch services
  const fetchServices = useCallback(async () => {
    if (!project || !env) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetchWithRetry(`/api/${project}/services/${env}`);
      if (response.ok) {
        const data = await response.json();
        setServices(data.services || []);
      } else {
        throw new Error(`Failed to fetch services: ${response.status}`);
      }
    } catch (err) {
      console.error('Error fetching services:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [project, env]);

  // Load services on mount and when project/env changes
  useEffect(() => {
    fetchServices();
  }, [fetchServices]);

  // Navigate to service detail
  const handleServiceClick = (service) => {
    const serviceName = service.serviceName || service.serviceArn?.split('/').pop();
    navigate(`/${project}/${env}/services/${serviceName}`);
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Services</h1>
          <p className="text-gray-500 mt-1">
            ECS services in {project} / {env}
          </p>
        </div>

        <button
          onClick={fetchServices}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4 mb-6">
          <div className="flex items-center gap-2 text-red-400">
            <AlertTriangle size={18} />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && services.length === 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg p-4 animate-pulse">
              <div className="h-6 bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-gray-800 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      )}

      {/* Services grid */}
      {!loading && services.length === 0 && !error && (
        <div className="text-center py-12">
          <Server size={48} className="mx-auto text-gray-600 mb-4" />
          <h3 className="text-lg font-medium text-gray-400">No services found</h3>
          <p className="text-gray-500 mt-1">
            No ECS services found in this environment.
          </p>
        </div>
      )}

      {services.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {services.map((service) => (
            <ServiceCard
              key={service.serviceArn || service.serviceName}
              service={service}
              onClick={() => handleServiceClick(service)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
