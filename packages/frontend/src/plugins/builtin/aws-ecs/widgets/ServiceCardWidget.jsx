/**
 * Service Card Widget - AWS ECS Plugin
 */
import { Server, CheckCircle, XCircle } from 'lucide-react';

export default function ServiceCardWidget({ projectId, environment, config, onNavigate }) {
  // This widget shows a summary of services status
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <Server size={18} className="text-blue-400" />
        <h3 className="font-medium">ECS Services</h3>
      </div>
      <p className="text-sm text-gray-500">
        Click to view services in {projectId}/{environment}
      </p>
      <button
        onClick={() => onNavigate?.(`/${projectId}/${environment}/services`)}
        className="mt-3 text-sm text-blue-400 hover:underline"
      >
        View all services →
      </button>
    </div>
  );
}
