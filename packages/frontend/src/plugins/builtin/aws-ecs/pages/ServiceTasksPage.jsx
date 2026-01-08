/**
 * Service Tasks Page - AWS ECS Plugin
 */
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export default function ServiceTasksPage({ params }) {
  const navigate = useNavigate();
  const { project, env, service } = params;

  return (
    <div className="p-6">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(`/${project}/${env}/services/${service}`)}
          className="p-2 hover:bg-gray-800 rounded-lg"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-semibold">Tasks: {service}</h1>
      </div>
      <p className="text-gray-500">Task list will be displayed here.</p>
    </div>
  );
}
