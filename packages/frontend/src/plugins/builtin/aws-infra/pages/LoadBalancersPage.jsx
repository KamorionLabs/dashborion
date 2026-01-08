/**
 * Load Balancers Page - AWS Infrastructure Plugin
 */
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Globe, CheckCircle, XCircle } from 'lucide-react';

export default function LoadBalancersPage({ params }) {
  const navigate = useNavigate();
  const { project, env } = params;

  return (
    <div className="p-6">
      <div className="flex items-center gap-4 mb-6">
        <button
          onClick={() => navigate(`/${project}/${env}/infrastructure`)}
          className="p-2 hover:bg-gray-800 rounded-lg"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-semibold">Load Balancers</h1>
      </div>

      <div className="text-center py-12 border border-dashed border-gray-700 rounded-lg">
        <Globe size={48} className="mx-auto text-gray-600 mb-4" />
        <p className="text-gray-500">ALB and Target Group status will be displayed here.</p>
      </div>
    </div>
  );
}
