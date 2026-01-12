/**
 * HeroSummary - Overview section with animated donut charts
 *
 * Shows source and destination health with animated sync flow between them.
 */

import SyncStatusRing from './SyncStatusRing';
import SyncFlowConnector from './SyncFlowConnector';

export default function HeroSummary({
  sourceLabel = 'Source',
  destinationLabel = 'Destination',
  overallStatus = 'pending',
  overallSyncPercentage = 0,
  categories = {},
  lastUpdated,
}) {
  // Calculate category percentages
  const categoryStats = Object.entries(categories).map(([name, stats]) => ({
    name,
    total: stats.total || 0,
    synced: stats.synced || 0,
    percentage: stats.total > 0 ? Math.round((stats.synced / stats.total) * 100) : 0,
  }));

  // Calculate source/dest "health" based on sync percentage
  const sourceHealth = Math.min(100, overallSyncPercentage + 5);
  const destHealth = overallSyncPercentage;

  const formatTime = (date) => {
    if (!date) return null;
    const d = new Date(date);
    return d.toLocaleString();
  };

  return (
    <div className="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
      {/* Title row */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold text-gray-100">Environment Comparison</h2>
        {lastUpdated && (
          <span className="text-sm text-gray-500">
            Last updated: {formatTime(lastUpdated)}
          </span>
        )}
      </div>

      {/* Main hero section */}
      <div className="flex items-center justify-center gap-8 py-6">
        {/* Source */}
        <div className="flex flex-col items-center">
          <SyncStatusRing
            percentage={sourceHealth}
            status={overallStatus === 'synced' ? 'synced' : 'differs'}
            size={160}
            strokeWidth={12}
            sublabel={sourceLabel}
          />
          <span className="mt-2 text-sm text-gray-400">Reference</span>
        </div>

        {/* Flow connector */}
        <div className="flex-shrink-0">
          <SyncFlowConnector
            status={overallStatus}
            percentage={overallSyncPercentage}
            width={220}
            height={80}
            showPercentage={true}
          />
        </div>

        {/* Destination */}
        <div className="flex flex-col items-center">
          <SyncStatusRing
            percentage={destHealth}
            status={overallStatus}
            size={160}
            strokeWidth={12}
            sublabel={destinationLabel}
          />
          <span className="mt-2 text-sm text-gray-400">Target</span>
        </div>
      </div>

      {/* Category breakdown */}
      {categoryStats.length > 0 && (
        <div className="mt-6 pt-6 border-t border-gray-700">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Sync by Category</h3>
          <div className="grid grid-cols-3 gap-4">
            {categoryStats.map(({ name, total, synced, percentage }) => (
              <div key={name} className="bg-gray-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-300 capitalize">{name}</span>
                  <span className={`text-sm font-bold ${
                    percentage >= 90 ? 'text-green-400' :
                    percentage >= 50 ? 'text-yellow-400' : 'text-red-400'
                  }`}>
                    {percentage}%
                  </span>
                </div>
                <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      percentage >= 90 ? 'bg-green-500' :
                      percentage >= 50 ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
                <div className="mt-1 text-xs text-gray-500">
                  {synced} / {total} checks
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick stats */}
      <div className="mt-6 grid grid-cols-4 gap-4">
        <QuickStat
          label="Total Checks"
          value={categoryStats.reduce((acc, c) => acc + c.total, 0)}
          color="text-blue-400"
        />
        <QuickStat
          label="Synced"
          value={categoryStats.reduce((acc, c) => acc + c.synced, 0)}
          color="text-green-400"
        />
        <QuickStat
          label="Differs"
          value={categoryStats.reduce((acc, c) => acc + (c.total - c.synced), 0)}
          color="text-yellow-400"
        />
        <QuickStat
          label="Overall"
          value={`${Math.round(overallSyncPercentage)}%`}
          color={overallStatus === 'synced' ? 'text-green-400' : 'text-yellow-400'}
        />
      </div>
    </div>
  );
}

function QuickStat({ label, value, color }) {
  return (
    <div className="bg-gray-800 rounded-lg p-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}
