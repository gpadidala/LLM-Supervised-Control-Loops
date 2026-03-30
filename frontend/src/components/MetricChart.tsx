import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  ComposedChart,
  ReferenceLine,
} from 'recharts'
import { format } from 'date-fns'

interface MetricChartProps {
  title: string
  data: { timestamp: string; value: number; q10?: number; q90?: number }[]
  color?: string
  showBands?: boolean
  threshold?: number
  height?: number
}

export default function MetricChart({
  title,
  data,
  color = '#3b82f6',
  showBands = false,
  threshold,
  height = 200,
}: MetricChartProps) {
  const formatTime = (ts: string) => {
    try {
      return format(new Date(ts), 'HH:mm:ss')
    } catch {
      return ts
    }
  }

  const formatValue = (val: number) => {
    if (Math.abs(val) >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`
    if (Math.abs(val) >= 1_000) return `${(val / 1_000).toFixed(1)}K`
    return val.toFixed(2)
  }

  if (data.length === 0) {
    return (
      <div className="card">
        <div className="card-header">{title}</div>
        <div
          className="flex items-center justify-center text-slate-500 text-sm"
          style={{ height }}
        >
          No data available
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-header">{title}</div>
      <ResponsiveContainer width="100%" height={height}>
        {showBands ? (
          <ComposedChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTime}
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tickFormatter={formatValue}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #475569',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              labelFormatter={formatTime}
              formatter={(value: number) => [formatValue(value), '']}
            />
            <Area
              dataKey="q90"
              stroke="none"
              fill={color}
              fillOpacity={0.1}
              name="Q90"
            />
            <Area
              dataKey="q10"
              stroke="none"
              fill="#0f172a"
              fillOpacity={1}
              name="Q10"
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={false}
              name="Value"
            />
            {threshold !== undefined && (
              <ReferenceLine
                y={threshold}
                stroke="#ef4444"
                strokeDasharray="5 5"
                label={{
                  value: 'SLO',
                  position: 'right',
                  fill: '#ef4444',
                  fontSize: 10,
                }}
              />
            )}
          </ComposedChart>
        ) : (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTime}
              stroke="#64748b"
              fontSize={10}
              tickLine={false}
            />
            <YAxis
              stroke="#64748b"
              fontSize={10}
              tickFormatter={formatValue}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: '#1e293b',
                border: '1px solid #475569',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              labelFormatter={formatTime}
              formatter={(value: number) => [formatValue(value), '']}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: color }}
            />
            {threshold !== undefined && (
              <ReferenceLine
                y={threshold}
                stroke="#ef4444"
                strokeDasharray="5 5"
                label={{
                  value: 'SLO',
                  position: 'right',
                  fill: '#ef4444',
                  fontSize: 10,
                }}
              />
            )}
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
