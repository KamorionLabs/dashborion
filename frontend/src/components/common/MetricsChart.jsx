import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

export default function MetricsChart({ title, data, color, icon }) {
  if (!data || data.length === 0) {
    return (
      <div className="h-10 flex items-center justify-center text-gray-500 text-xs">
        No {title} data
      </div>
    )
  }

  const latestValue = data[data.length - 1]?.value || 0

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1 text-xs text-gray-400">
          {icon}
          <span>{title}</span>
        </div>
        <span className="text-xs font-medium" style={{ color }}>{latestValue.toFixed(1)}%</span>
      </div>
      <div className="h-10">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <XAxis dataKey="timestamp" hide />
            <YAxis domain={[0, 100]} hide />
            <Tooltip
              contentStyle={{
                background: '#1f2937',
                border: '1px solid #374151',
                borderRadius: '0.375rem',
                fontSize: '0.75rem'
              }}
              formatter={(value) => [`${value.toFixed(1)}%`, title]}
              labelFormatter={(label) => new Date(label).toLocaleTimeString()}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={1.5}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
