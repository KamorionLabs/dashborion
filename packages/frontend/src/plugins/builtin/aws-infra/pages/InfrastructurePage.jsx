/**
 * Infrastructure Overview Page - AWS Infrastructure Plugin
 */
import { useNavigate } from 'react-router-dom';
import { Server, Database, Globe, Cpu } from 'lucide-react';

export default function InfrastructurePage({ params }) {
  const navigate = useNavigate();
  const { project, env } = params;

  const sections = [
    {
      id: 'load-balancers',
      title: 'Load Balancers',
      description: 'Application Load Balancers and Target Groups',
      icon: Globe,
      path: `/${project}/${env}/infrastructure/load-balancers`,
    },
    {
      id: 'databases',
      title: 'Databases',
      description: 'RDS PostgreSQL and MySQL instances',
      icon: Database,
      path: `/${project}/${env}/infrastructure/databases`,
    },
    {
      id: 'cache',
      title: 'Cache',
      description: 'ElastiCache Valkey/Redis clusters',
      icon: Cpu,
      path: `/${project}/${env}/infrastructure/cache`,
    },
  ];

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-white mb-2">Infrastructure</h1>
      <p className="text-gray-500 mb-6">{project} / {env}</p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {sections.map((section) => {
          const Icon = section.icon;
          return (
            <button
              key={section.id}
              onClick={() => navigate(section.path)}
              className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-left hover:border-gray-700 transition-colors"
            >
              <div className="flex items-center gap-3 mb-3">
                <Icon size={24} className="text-blue-400" />
                <h2 className="text-lg font-medium">{section.title}</h2>
              </div>
              <p className="text-gray-500 text-sm">{section.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
