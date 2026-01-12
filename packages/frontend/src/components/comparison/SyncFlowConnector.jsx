/**
 * SyncFlowConnector - Animated flow line between source and destination
 *
 * Shows sync status with animated gradient flow.
 */

const STATUS_COLORS = {
  synced: '#22c55e',
  differs: '#f59e0b',
  critical: '#ef4444',
  pending: '#6b7280',
};

export default function SyncFlowConnector({
  status = 'synced',
  percentage = 100,
  width = 200,
  height = 60,
  showPercentage = true,
  label = '',
}) {
  const color = STATUS_COLORS[status] || STATUS_COLORS.pending;
  const gradientId = `sync-flow-${Math.random().toString(36).substr(2, 9)}`;

  return (
    <div className="flex flex-col items-center">
      <svg width={width} height={height} className="overflow-visible">
        <defs>
          {/* Animated gradient for flow effect */}
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={color} stopOpacity="0">
              <animate
                attributeName="offset"
                values="-0.5;1"
                dur="2s"
                repeatCount="indefinite"
              />
            </stop>
            <stop offset="50%" stopColor={color} stopOpacity="1">
              <animate
                attributeName="offset"
                values="0;1.5"
                dur="2s"
                repeatCount="indefinite"
              />
            </stop>
            <stop offset="100%" stopColor={color} stopOpacity="0">
              <animate
                attributeName="offset"
                values="0.5;2"
                dur="2s"
                repeatCount="indefinite"
              />
            </stop>
          </linearGradient>

          {/* Arrow marker */}
          <marker
            id={`arrow-${gradientId}`}
            markerWidth="10"
            markerHeight="7"
            refX="9"
            refY="3.5"
            orient="auto"
          >
            <polygon points="0 0, 10 3.5, 0 7" fill={color} />
          </marker>
        </defs>

        {/* Background line */}
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#374151"
          strokeWidth="4"
          strokeLinecap="round"
        />

        {/* Progress line */}
        <line
          x1="0"
          y1={height / 2}
          x2={width * (percentage / 100)}
          y2={height / 2}
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          opacity="0.3"
        />

        {/* Animated flow line */}
        <line
          x1="0"
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke={`url(#${gradientId})`}
          strokeWidth="4"
          strokeLinecap="round"
          markerEnd={`url(#arrow-${gradientId})`}
        />

        {/* Sync indicator dots */}
        <circle cx="10" cy={height / 2} r="6" fill="#1f2937" stroke={color} strokeWidth="2" />
        <circle cx={width - 10} cy={height / 2} r="6" fill="#1f2937" stroke={color} strokeWidth="2" />

        {/* Percentage text */}
        {showPercentage && (
          <text
            x={width / 2}
            y={height / 2 - 15}
            textAnchor="middle"
            fill={color}
            fontSize="14"
            fontWeight="bold"
          >
            {Math.round(percentage)}% sync
          </text>
        )}
      </svg>

      {/* Label below */}
      {label && (
        <span className="text-xs text-gray-500 mt-1">{label}</span>
      )}
    </div>
  );
}
