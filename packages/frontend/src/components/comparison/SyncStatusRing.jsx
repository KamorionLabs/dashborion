/**
 * SyncStatusRing - Animated donut chart showing sync percentage
 *
 * Displays a circular progress indicator with animated fill
 * and percentage text in the center.
 */

import { useMemo } from 'react';

const STATUS_COLORS = {
  synced: { stroke: '#22c55e', bg: 'rgba(34, 197, 94, 0.1)', text: 'text-green-400' },
  differs: { stroke: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)', text: 'text-yellow-400' },
  critical: { stroke: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)', text: 'text-red-400' },
  pending: { stroke: '#6b7280', bg: 'rgba(107, 114, 128, 0.1)', text: 'text-gray-400' },
  error: { stroke: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)', text: 'text-red-400' },
};

export default function SyncStatusRing({
  percentage = 0,
  status = 'pending',
  size = 140,
  strokeWidth = 10,
  label = '',
  sublabel = '',
  animate = true,
}) {
  const colors = STATUS_COLORS[status] || STATUS_COLORS.pending;

  const { radius, circumference, dashOffset } = useMemo(() => {
    const r = (size - strokeWidth) / 2;
    const c = 2 * Math.PI * r;
    const offset = c - (percentage / 100) * c;
    return { radius: r, circumference: c, dashOffset: offset };
  }, [size, strokeWidth, percentage]);

  const center = size / 2;

  return (
    <div className="relative inline-flex flex-col items-center">
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill={colors.bg}
          stroke="#374151"
          strokeWidth={strokeWidth}
        />

        {/* Progress circle */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={colors.stroke}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          className={animate ? 'transition-all duration-1000 ease-out' : ''}
        />

        {/* Glow effect for synced status */}
        {status === 'synced' && percentage >= 95 && (
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke={colors.stroke}
            strokeWidth={strokeWidth / 2}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            opacity="0.3"
            filter="blur(4px)"
          />
        )}
      </svg>

      {/* Center content */}
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-2xl font-bold ${colors.text}`}>
          {Math.round(percentage)}%
        </span>
        {label && (
          <span className="text-xs text-gray-400 mt-1">{label}</span>
        )}
      </div>

      {/* Sublabel below */}
      {sublabel && (
        <span className={`mt-2 text-sm font-medium ${colors.text}`}>
          {sublabel}
        </span>
      )}
    </div>
  );
}
