/**
 * Pipelines Page - AWS CI/CD Plugin
 */
import { GitBranch } from 'lucide-react';

export default function PipelinesPage({ params }) {
  const { project, env } = params;

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-white mb-2">Pipelines</h1>
      <p className="text-gray-500 mb-6">{project} / {env}</p>

      <div className="text-center py-12 border border-dashed border-gray-700 rounded-lg">
        <GitBranch size={48} className="mx-auto text-gray-600 mb-4" />
        <p className="text-gray-500">Pipeline list will be displayed here.</p>
      </div>
    </div>
  );
}
