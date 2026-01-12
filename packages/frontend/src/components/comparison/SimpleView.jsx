/**
 * SimpleView - Simplified comparison view for non-technical users
 *
 * Shows only essential information:
 * - Overall sync status with big visual indicator
 * - Category summary as simple colored bars
 * - Clear messaging (All synced / Issues detected)
 */

import { CheckCircle, AlertTriangle, XCircle, ArrowRight, Clock } from 'lucide-react';
import SyncStatusRing from './SyncStatusRing';

/**
 * Get status config based on sync percentage and status
 */
function getStatusConfig(percentage, status, pendingChecks = 0, totalChecks = 0) {
  // Handle incomplete states first (checks missing data)
  if (status?.startsWith('incomplete')) {
    const completedChecks = totalChecks - pendingChecks;
    return {
      icon: AlertTriangle,
      color: 'text-orange-400',
      bgColor: 'bg-orange-500/10',
      borderColor: 'border-orange-500/30',
      message: 'Comparison Incomplete',
      description: `Only ${completedChecks} of ${totalChecks} checks have data. Trigger comparison to get full results.`,
    };
  }

  if (status === 'synced' || percentage >= 95) {
    return {
      icon: CheckCircle,
      color: 'text-green-400',
      bgColor: 'bg-green-500/10',
      borderColor: 'border-green-500/30',
      message: 'Environments Synchronized',
      description: 'All checks are passing. Source and destination are in sync.',
    };
  }
  if (percentage >= 70) {
    return {
      icon: AlertTriangle,
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-500/10',
      borderColor: 'border-yellow-500/30',
      message: 'Minor Differences Detected',
      description: 'Some items differ between environments. Review recommended.',
    };
  }
  return {
    icon: XCircle,
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    message: 'Significant Differences',
    description: 'Major differences detected. Action required.',
  };
}

/**
 * Category Summary Card
 */
function CategoryCard({ name, synced, total, percentage }) {
  const getColor = () => {
    if (total === 0) return 'gray';
    if (percentage >= 90) return 'green';
    if (percentage >= 50) return 'yellow';
    return 'red';
  };

  const color = getColor();
  const colorClasses = {
    green: { bar: 'bg-green-500', text: 'text-green-400', bg: 'bg-green-500/10' },
    yellow: { bar: 'bg-yellow-500', text: 'text-yellow-400', bg: 'bg-yellow-500/10' },
    red: { bar: 'bg-red-500', text: 'text-red-400', bg: 'bg-red-500/10' },
    gray: { bar: 'bg-gray-600', text: 'text-gray-400', bg: 'bg-gray-500/10' },
  };

  const classes = colorClasses[color];

  return (
    <div className={`p-4 rounded-xl border border-gray-700 ${classes.bg}`}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-gray-200 capitalize">{name}</span>
        <span className={`text-lg font-bold ${classes.text}`}>
          {total > 0 ? `${percentage}%` : '-'}
        </span>
      </div>
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${classes.bar} transition-all duration-700 ease-out`}
          style={{ width: `${total > 0 ? percentage : 0}%` }}
        />
      </div>
      <div className="mt-2 text-xs text-gray-500">
        {total > 0 ? `${synced} / ${total} checks synced` : 'No checks configured'}
      </div>
    </div>
  );
}

/**
 * Big Status Indicator
 */
function BigStatusIndicator({ percentage, status, sourceLabel, destinationLabel, pendingChecks, totalChecks }) {
  const config = getStatusConfig(percentage, status, pendingChecks, totalChecks);
  const Icon = config.icon;

  return (
    <div className={`
      p-8 rounded-2xl border-2 ${config.borderColor} ${config.bgColor}
      flex flex-col items-center text-center
    `}>
      {/* Status icon and message */}
      <div className="flex items-center gap-3 mb-4">
        <Icon className={`w-10 h-10 ${config.color}`} />
        <div className="text-left">
          <h2 className={`text-2xl font-bold ${config.color}`}>{config.message}</h2>
          <p className="text-gray-400 text-sm">{config.description}</p>
        </div>
      </div>

      {/* Visual comparison */}
      <div className="flex items-center justify-center gap-8 mt-6">
        <div className="flex flex-col items-center">
          <SyncStatusRing
            percentage={100}
            status="synced"
            size={100}
            strokeWidth={8}
            sublabel={sourceLabel}
          />
          <span className="mt-2 text-xs text-gray-500">Reference</span>
        </div>

        <div className="flex flex-col items-center">
          <div className={`text-4xl font-bold ${config.color}`}>
            {Math.round(percentage)}%
          </div>
          <span className="text-sm text-gray-400">sync</span>
        </div>

        <div className="flex flex-col items-center">
          <SyncStatusRing
            percentage={percentage}
            status={status}
            size={100}
            strokeWidth={8}
            sublabel={destinationLabel}
          />
          <span className="mt-2 text-xs text-gray-500">Target</span>
        </div>
      </div>
    </div>
  );
}

/**
 * Last Update Info
 */
function LastUpdateInfo({ lastUpdated }) {
  if (!lastUpdated) return null;

  const date = new Date(lastUpdated);
  const now = new Date();
  const diffMinutes = Math.round((now - date) / 60000);
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();

  let timeAgo;
  if (diffMinutes < 1) timeAgo = 'Just now';
  else if (diffMinutes < 60) timeAgo = `${diffMinutes} min ago`;
  else if (diffMinutes < 1440) timeAgo = `${Math.round(diffMinutes / 60)} hours ago`;
  else timeAgo = date.toLocaleDateString();

  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  let dateDisplay;
  if (isToday) {
    dateDisplay = `Today ${time}`;
  } else if (isYesterday) {
    dateDisplay = `Yesterday ${time}`;
  } else {
    dateDisplay = date.toLocaleDateString([], { day: '2-digit', month: '2-digit' }) + ' ' + time;
  }

  return (
    <div className="text-center text-sm text-gray-500 flex items-center justify-center gap-2">
      <Clock className="w-3.5 h-3.5" />
      <span className="text-gray-400">{dateDisplay}</span>
      <span className="text-gray-600">({timeAgo})</span>
    </div>
  );
}

/**
 * Main SimpleView Component
 */
export default function SimpleView({ data, onSwitchToTechnical }) {
  const {
    sourceLabel = 'Source',
    destinationLabel = 'Destination',
    overallStatus = 'pending',
    overallSyncPercentage = 0,
    categories = {},
    lastUpdated,
    totalChecks = 0,
    completedChecks = 0,
    pendingChecks = 0,
  } = data || {};

  // Calculate category stats
  const categoryStats = Object.entries(categories).map(([name, stats]) => ({
    name,
    total: stats.total || 0,
    synced: stats.synced || 0,
    percentage: stats.total > 0 ? Math.round((stats.synced / stats.total) * 100) : 0,
  }));

  return (
    <div className="space-y-6">
      {/* Big Status Indicator */}
      <BigStatusIndicator
        percentage={overallSyncPercentage}
        status={overallStatus}
        sourceLabel={sourceLabel}
        destinationLabel={destinationLabel}
        pendingChecks={pendingChecks}
        totalChecks={totalChecks}
      />

      {/* Category Summary */}
      {categoryStats.length > 0 && (
        <div className="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-200 mb-4">Sync by Category</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {categoryStats.map((cat) => (
              <CategoryCard
                key={cat.name}
                name={cat.name}
                synced={cat.synced}
                total={cat.total}
                percentage={cat.percentage}
              />
            ))}
          </div>
        </div>
      )}

      {/* Last Update */}
      <LastUpdateInfo lastUpdated={lastUpdated} />

      {/* Link to detailed view */}
      <div className="text-center">
        <button
          onClick={onSwitchToTechnical}
          className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 text-sm"
        >
          View technical details
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
