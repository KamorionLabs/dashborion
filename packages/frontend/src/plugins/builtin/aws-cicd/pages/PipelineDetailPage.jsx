/**
 * Pipeline Detail Page - AWS CI/CD Plugin
 */
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, GitBranch } from 'lucide-react';

export default function PipelineDetailPage({ params }) {
  const navigate = useNavigate();
  const { project, env, pipeline } = params;

  return (
    <div className="p-6">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(`/${project}/${env}/pipelines`)}
          className="p-2 hover:bg-gray-800 rounded-lg"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-semibold">{pipeline}</h1>
      </div>
      <p className="text-gray-500">Pipeline details will be displayed here.</p>
    </div>
  );
}
