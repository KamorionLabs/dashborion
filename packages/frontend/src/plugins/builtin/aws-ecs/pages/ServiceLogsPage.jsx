/**
 * Service Logs Page - AWS ECS Plugin
 */
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { TabbedLogsPanel } from '../../../../components/logs';

export default function ServiceLogsPage({ params }) {
  const navigate = useNavigate();
  const { project, env, service } = params;

  return (
    <div className="h-full flex flex-col">
      <div className="p-4 border-b border-gray-800 flex items-center gap-4">
        <button
          onClick={() => navigate(`/${project}/${env}/services/${service}`)}
          className="p-2 hover:bg-gray-800 rounded-lg"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-semibold">Logs: {service}</h1>
      </div>
      <div className="flex-1">
        <TabbedLogsPanel
          projectId={project}
          env={env}
          service={service}
          autoTail={true}
        />
      </div>
    </div>
  );
}
