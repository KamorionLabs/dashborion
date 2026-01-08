/**
 * Service Status Widget - AWS ECS Plugin
 */
import { CheckCircle, XCircle, Clock } from 'lucide-react';

export default function ServiceStatusWidget({ projectId, environment, config }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h3 className="font-medium mb-3">Service Status</h3>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-gray-400">Running</span>
          <span className="flex items-center gap-1 text-green-400">
            <CheckCircle size={14} /> 0
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-400">Pending</span>
          <span className="flex items-center gap-1 text-yellow-400">
            <Clock size={14} /> 0
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-400">Failed</span>
          <span className="flex items-center gap-1 text-red-400">
            <XCircle size={14} /> 0
          </span>
        </div>
      </div>
    </div>
  );
}
