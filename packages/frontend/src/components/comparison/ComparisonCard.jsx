/**
 * ComparisonCard - Individual comparison item card
 *
 * Shows sync status for a specific check type with progress bar and counts.
 */

import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  Server,
  Database,
  Network,
  Key,
  Shield,
  Globe,
  HardDrive,
  Box,
} from 'lucide-react';

const STATUS_CONFIG = {
  synced: {
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    hoverBorder: 'hover:border-green-500/60',
    progress: 'bg-green-500',
    icon: CheckCircle,
    iconColor: 'text-green-400',
    badge: 'bg-green-500/20 text-green-400',
  },
  differs: {
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    hoverBorder: 'hover:border-yellow-500/60',
    progress: 'bg-yellow-500',
    icon: AlertTriangle,
    iconColor: 'text-yellow-400',
    badge: 'bg-yellow-500/20 text-yellow-400',
  },
  critical: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    hoverBorder: 'hover:border-red-500/60',
    progress: 'bg-red-500',
    icon: XCircle,
    iconColor: 'text-red-400',
    badge: 'bg-red-500/20 text-red-400',
  },
  pending: {
    bg: 'bg-gray-500/10',
    border: 'border-gray-500/30',
    hoverBorder: 'hover:border-gray-500/60',
    progress: 'bg-gray-500',
    icon: Clock,
    iconColor: 'text-gray-400',
    badge: 'bg-gray-500/20 text-gray-400',
  },
  error: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    hoverBorder: 'hover:border-red-500/60',
    progress: 'bg-red-500',
    icon: XCircle,
    iconColor: 'text-red-400',
    badge: 'bg-red-500/20 text-red-400',
  },
};

const CHECK_TYPE_ICONS = {
  'k8s-pods-compare': Box,
  'k8s-services-compare': Server,
  'k8s-ingress-compare': Globe,
  'k8s-pvc-compare': HardDrive,
  'k8s-secrets-compare': Key,
  'config-sm-compare': Key,
  'config-ssm-compare': Database,
  'net-dns-compare': Globe,
  'net-alb-compare': Network,
  'net-cloudfront-compare': Globe,
  'net-sg-compare': Shield,
};

export default function ComparisonCard({
  checkType,
  label,
  status = 'pending',
  sourceCount = 0,
  destinationCount = 0,
  syncedCount = 0,
  differsCount = 0,
  onlySourceCount = 0,
  onlyDestinationCount = 0,
  syncPercentage = 0,
  lastUpdated,
  onClick,
  sourceLabel = 'Source',
  destinationLabel = 'Destination',
}) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const StatusIcon = config.icon;
  const TypeIcon = CHECK_TYPE_ICONS[checkType] || Server;

  const formatDateTime = (date) => {
    if (!date) return null;
    const d = new Date(date);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = d.toDateString() === yesterday.toDateString();

    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (isToday) {
      return `Today ${time}`;
    } else if (isYesterday) {
      return `Yesterday ${time}`;
    } else {
      return d.toLocaleDateString([], { day: '2-digit', month: '2-digit' }) + ' ' + time;
    }
  };

  return (
    <div
      onClick={onClick}
      className={`
        group rounded-lg border p-4 cursor-pointer
        transition-all duration-300 ease-out
        hover:shadow-lg hover:shadow-black/20 hover:scale-[1.02]
        ${config.bg} ${config.border} ${config.hoverBorder}
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${config.bg}`}>
            <TypeIcon className={`w-5 h-5 ${config.iconColor}`} />
          </div>
          <span className="font-semibold text-gray-100">{label}</span>
        </div>
        <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium ${config.badge}`}>
          <StatusIcon className="w-3.5 h-3.5" />
          <span className="capitalize">{status}</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden mb-3">
        <div
          className={`h-full ${config.progress} transition-all duration-700 ease-out`}
          style={{ width: `${syncPercentage}%` }}
        />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex justify-between">
          <span className="text-gray-500">{sourceLabel}:</span>
          <span className="text-gray-300 font-medium">{sourceCount}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-500">{destinationLabel}:</span>
          <span className="text-gray-300 font-medium">{destinationCount}</span>
        </div>
      </div>

      {/* Sync details on hover */}
      <div className="mt-3 pt-3 border-t border-gray-700/50 grid grid-cols-3 gap-2 text-xs">
        <div className="text-center">
          <span className="text-green-400 font-medium">{syncedCount}</span>
          <span className="text-gray-500 block">synced</span>
        </div>
        <div className="text-center">
          <span className="text-yellow-400 font-medium">{onlySourceCount + onlyDestinationCount}</span>
          <span className="text-gray-500 block">missing</span>
        </div>
        <div className="text-center">
          <span className="text-red-400 font-medium">{differsCount}</span>
          <span className="text-gray-500 block">differs</span>
        </div>
      </div>

      {/* Last updated */}
      <div className="mt-2 text-xs text-gray-500 text-right">
        {lastUpdated ? (
          <>
            <Clock className="w-3 h-3 inline mr-1" />
            {formatDateTime(lastUpdated)}
          </>
        ) : (
          <span className="text-gray-600 italic">No data yet</span>
        )}
      </div>
    </div>
  );
}
