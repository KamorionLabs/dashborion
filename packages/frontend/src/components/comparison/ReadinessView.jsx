/**
 * ReadinessView - Environment readiness status view
 *
 * Shows deployment/preparation phases in a visual matrix.
 * Phases are configurable via comparison.readiness config.
 *
 * Default phases:
 * - Infrastructure: cluster, networking, storage
 * - Data: database, replication, secrets
 * - Application: deployment, configuration, CI/CD
 * - Access: external access, team access, routing
 * - Validation: tests, acceptance
 * - Operations: monitoring, backup, documentation
 */

import { useState } from 'react';
import { CheckCircle, Clock, AlertCircle, Circle, ArrowRight, ExternalLink, Settings } from 'lucide-react';

// Status definitions
const STATUS = {
  done: { label: 'Done', icon: CheckCircle, color: 'text-green-400', bgColor: 'bg-green-500/20', borderColor: 'border-green-500/30' },
  'in-progress': { label: 'In Progress', icon: Clock, color: 'text-yellow-400', bgColor: 'bg-yellow-500/20', borderColor: 'border-yellow-500/30' },
  todo: { label: 'Todo', icon: Circle, color: 'text-gray-500', bgColor: 'bg-gray-500/10', borderColor: 'border-gray-500/30' },
  blocked: { label: 'Blocked', icon: AlertCircle, color: 'text-red-400', bgColor: 'bg-red-500/20', borderColor: 'border-red-500/30' },
};

// Default phases - used when no config provided
const DEFAULT_PHASES = [
  {
    id: 'infrastructure',
    label: 'Infrastructure',
    items: [
      { id: 'cluster', label: 'Cluster', checkTypes: ['k8s:pods'] },
      { id: 'networking', label: 'Networking', checkTypes: ['k8s:ingress', 'net:alb', 'net:sg'] },
      { id: 'storage', label: 'Storage', checkTypes: ['k8s:pvc'] },
    ],
  },
  {
    id: 'data',
    label: 'Data Sync',
    items: [
      { id: 'database', label: 'Database' },
      { id: 'replication', label: 'Replication' },
      { id: 'secrets', label: 'Secrets', checkTypes: ['k8s:secrets', 'config:sm'] },
    ],
  },
  {
    id: 'application',
    label: 'Application',
    items: [
      { id: 'deployment', label: 'Deployment', checkTypes: ['k8s:pods', 'k8s:services'] },
      { id: 'configuration', label: 'Configuration', checkTypes: ['config:ssm'] },
      { id: 'cicd', label: 'CI/CD Pipeline' },
    ],
  },
  {
    id: 'access',
    label: 'Access',
    items: [
      { id: 'external', label: 'External Access' },
      { id: 'teams', label: 'Team Access' },
      { id: 'dns', label: 'DNS / Routing', checkTypes: ['net:dns', 'net:cloudfront'] },
    ],
  },
  {
    id: 'validation',
    label: 'Validation',
    items: [
      { id: 'tests', label: 'Tests' },
      { id: 'acceptance', label: 'Acceptance' },
    ],
  },
  {
    id: 'operations',
    label: 'Operations',
    items: [
      { id: 'monitoring', label: 'Monitoring' },
      { id: 'backup', label: 'Backup' },
      { id: 'documentation', label: 'Documentation' },
    ],
  },
];

/**
 * Map comparison data to readiness statuses based on check types
 */
function mapComparisonToReadiness(comparisonData, phases) {
  const statusMap = {};

  if (!comparisonData?.items) return statusMap;

  // Build reverse mapping: checkType -> itemIds
  const checkTypeToItems = {};
  phases.forEach((phase) => {
    phase.items.forEach((item) => {
      if (item.checkTypes) {
        item.checkTypes.forEach((ct) => {
          if (!checkTypeToItems[ct]) checkTypeToItems[ct] = [];
          checkTypeToItems[ct].push(item.id);
        });
      }
    });
  });

  // Map comparison items to readiness statuses
  comparisonData.items.forEach((item) => {
    const itemIds = checkTypeToItems[item.checkType] || [];

    itemIds.forEach((itemId) => {
      let status = 'todo';
      if (item.status === 'synced') status = 'done';
      else if (item.status === 'differs') status = 'in-progress';
      else if (item.status === 'pending') status = 'todo';

      // Keep best status (done > in-progress > todo)
      const priority = { done: 3, 'in-progress': 2, todo: 1, blocked: 0 };
      if (!statusMap[itemId] || priority[status] > priority[statusMap[itemId]]) {
        statusMap[itemId] = status;
      }
    });
  });

  return statusMap;
}

/**
 * Status Badge Component
 */
function StatusBadge({ status }) {
  const config = STATUS[status] || STATUS.todo;
  const Icon = config.icon;

  return (
    <span className={`
      inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
      ${config.bgColor} ${config.color} border ${config.borderColor}
    `}>
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  );
}

/**
 * Phase Progress Bar
 */
function PhaseProgress({ items, statusMap }) {
  const done = items.filter((i) => statusMap[i.id] === 'done').length;
  const total = items.length;
  const percentage = total > 0 ? Math.round((done / total) * 100) : 0;

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full bg-green-500 transition-all duration-500"
          style={{ width: `${percentage}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 min-w-[3rem]">
        {done}/{total}
      </span>
    </div>
  );
}

/**
 * Phase Card Component
 */
function PhaseCard({ phase, statusMap, expanded, onToggle }) {
  const done = phase.items.filter((i) => statusMap[i.id] === 'done').length;
  const total = phase.items.length;
  const allDone = done === total && total > 0;

  return (
    <div className={`
      bg-gray-800/50 rounded-xl border transition-all
      ${allDone ? 'border-green-500/30' : 'border-gray-700'}
    `}>
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full p-4 flex items-center justify-between text-left hover:bg-gray-800/50 rounded-t-xl"
      >
        <div className="flex items-center gap-3">
          {allDone ? (
            <CheckCircle className="w-5 h-5 text-green-400" />
          ) : (
            <Clock className="w-5 h-5 text-yellow-400" />
          )}
          <span className="font-medium text-gray-200">{phase.label}</span>
        </div>
        <div className="flex items-center gap-4">
          <PhaseProgress items={phase.items} statusMap={statusMap} />
          <ArrowRight className={`w-4 h-4 text-gray-500 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        </div>
      </button>

      {/* Items */}
      {expanded && (
        <div className="border-t border-gray-700 p-4 space-y-3">
          {phase.items.map((item) => (
            <div
              key={item.id}
              className="flex items-center justify-between py-2 px-3 bg-gray-800 rounded-lg"
            >
              <div>
                <span className="text-sm text-gray-200">{item.label}</span>
                {item.owner && (
                  <span className="ml-2 text-xs text-gray-500">({item.owner})</span>
                )}
              </div>
              <StatusBadge status={statusMap[item.id] || 'todo'} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Overall Progress Summary
 */
function OverallProgress({ phases, statusMap }) {
  let totalItems = 0;
  let doneItems = 0;
  let ongoingItems = 0;

  phases.forEach((phase) => {
    phase.items.forEach((item) => {
      totalItems++;
      if (statusMap[item.id] === 'done') doneItems++;
      else if (statusMap[item.id] === 'in-progress') ongoingItems++;
    });
  });

  const percentage = totalItems > 0 ? Math.round((doneItems / totalItems) * 100) : 0;

  return (
    <div className="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-gray-200">Overall Readiness</h3>
        <span className={`text-3xl font-bold ${
          percentage >= 90 ? 'text-green-400' :
          percentage >= 50 ? 'text-yellow-400' : 'text-red-400'
        }`}>
          {percentage}%
        </span>
      </div>

      <div className="h-3 bg-gray-700 rounded-full overflow-hidden mb-4">
        <div
          className={`h-full transition-all duration-700 ${
            percentage >= 90 ? 'bg-green-500' :
            percentage >= 50 ? 'bg-yellow-500' : 'bg-red-500'
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>

      <div className="grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-2xl font-bold text-green-400">{doneItems}</div>
          <div className="text-xs text-gray-500">Completed</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-yellow-400">{ongoingItems}</div>
          <div className="text-xs text-gray-500">In Progress</div>
        </div>
        <div>
          <div className="text-2xl font-bold text-gray-400">{totalItems - doneItems - ongoingItems}</div>
          <div className="text-xs text-gray-500">Todo</div>
        </div>
      </div>
    </div>
  );
}

/**
 * Main ReadinessView Component
 *
 * Props:
 * - comparisonData: Data from comparison API
 * - config: Optional readiness config with phases and statusUrl
 *   {
 *     phases: [...],        // Custom phases (uses defaults if not provided)
 *     statusUrl: "...",     // External status tracking URL (optional)
 *     statusUrlLabel: "..." // Label for the link (default: "View full status")
 *   }
 */
export default function ReadinessView({ project, sourceEnv, destEnv, comparisonData, config = {} }) {
  const [expandedPhases, setExpandedPhases] = useState(new Set(['infrastructure', 'data']));

  // Use phases from config or defaults
  const phases = config.phases || DEFAULT_PHASES;

  // Map comparison data to readiness statuses
  const autoStatusMap = mapComparisonToReadiness(comparisonData, phases);

  // Merge with manual statuses if provided
  const manualStatusMap = config.manualStatuses || {};
  const statusMap = { ...autoStatusMap, ...manualStatusMap };

  const togglePhase = (phaseId) => {
    setExpandedPhases((prev) => {
      const next = new Set(prev);
      if (next.has(phaseId)) next.delete(phaseId);
      else next.add(phaseId);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      {/* Overall Progress */}
      <OverallProgress phases={phases} statusMap={statusMap} />

      {/* Info Banner */}
      <div className="bg-blue-900/20 border border-blue-700/30 rounded-lg p-4 flex items-start gap-3">
        <Settings className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1">
          <p className="text-sm text-blue-300">
            Statuses are automatically derived from comparison checks where available.
            Items without linked checks show as "Todo" until manually updated.
          </p>
          {config.statusUrl && (
            <a
              href={config.statusUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300 mt-2"
            >
              {config.statusUrlLabel || 'View full status'}
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          )}
        </div>
      </div>

      {/* Phase Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {phases.map((phase) => (
          <PhaseCard
            key={phase.id}
            phase={phase}
            statusMap={statusMap}
            expanded={expandedPhases.has(phase.id)}
            onToggle={() => togglePhase(phase.id)}
          />
        ))}
      </div>
    </div>
  );
}
