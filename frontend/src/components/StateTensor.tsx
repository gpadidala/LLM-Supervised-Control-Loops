import { useState } from 'react'
import clsx from 'clsx'
import type { SystemState, AnomalyScore, MetricValue } from '@/types'

interface StateTensorProps {
  state: SystemState | null
}

const signalClasses = [
  { key: 'infrastructure', label: 'Infrastructure' },
  { key: 'application', label: 'Application' },
  { key: 'business', label: 'Business' },
  { key: 'network', label: 'Network' },
  { key: 'cost', label: 'Cost' },
] as const

type SignalKey = (typeof signalClasses)[number]['key']

function getAnomalyColor(zScore: number): string {
  const abs = Math.abs(zScore)
  if (abs < 1) return 'bg-green-500/40'
  if (abs < 2) return 'bg-green-500/60'
  if (abs < 2.5) return 'bg-yellow-500/50'
  if (abs < 3) return 'bg-yellow-500/70'
  if (abs < 3.5) return 'bg-orange-500/60'
  return 'bg-red-500/70'
}

function getTextColor(zScore: number): string {
  const abs = Math.abs(zScore)
  if (abs < 2) return 'text-green-300'
  if (abs < 3) return 'text-yellow-300'
  return 'text-red-300'
}

export default function StateTensor({ state }: StateTensorProps) {
  const [tooltip, setTooltip] = useState<{
    metric: string
    value: number
    zScore: number
    x: number
    y: number
  } | null>(null)

  if (!state) {
    return (
      <div className="card">
        <div className="card-header">State Tensor</div>
        <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
          No telemetry data
        </div>
      </div>
    )
  }

  const anomalyMap: Record<string, AnomalyScore> = {}
  if (state.derived?.anomaly_scores) {
    state.derived.anomaly_scores.forEach((a) => {
      anomalyMap[a.metric_name] = a
    })
  }

  // Collect all metrics per signal class
  const metricsGrid: { class: string; metrics: MetricValue[] }[] = signalClasses.map(
    (sc) => {
      const vector = state[sc.key as SignalKey]
      return {
        class: sc.label,
        metrics: vector?.metrics || [],
      }
    }
  )

  // Find max rows
  const maxRows = Math.max(...metricsGrid.map((g) => g.metrics.length), 1)

  return (
    <div className="card relative">
      <div className="card-header">State Tensor Heatmap</div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left text-slate-500 font-medium pb-2 pr-3 w-8">#</th>
              {signalClasses.map((sc) => (
                <th
                  key={sc.key}
                  className="text-center text-slate-400 font-medium pb-2 px-1"
                >
                  {sc.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: maxRows }, (_, rowIdx) => (
              <tr key={rowIdx}>
                <td className="text-slate-600 py-0.5 pr-3">{rowIdx + 1}</td>
                {metricsGrid.map((col) => {
                  const metric = col.metrics[rowIdx]
                  if (!metric) {
                    return (
                      <td key={col.class + rowIdx} className="p-0.5">
                        <div className="w-full h-8 bg-slate-800/30 rounded" />
                      </td>
                    )
                  }
                  const anomaly = anomalyMap[metric.name]
                  const zScore = anomaly?.z_score ?? 0

                  return (
                    <td key={col.class + rowIdx} className="p-0.5">
                      <div
                        className={clsx(
                          'w-full h-8 rounded flex items-center justify-center cursor-pointer transition-all hover:ring-1 hover:ring-slate-400',
                          getAnomalyColor(zScore)
                        )}
                        onMouseEnter={(e) => {
                          const rect = e.currentTarget.getBoundingClientRect()
                          setTooltip({
                            metric: metric.name,
                            value: metric.value,
                            zScore,
                            x: rect.left + rect.width / 2,
                            y: rect.top,
                          })
                        }}
                        onMouseLeave={() => setTooltip(null)}
                      >
                        <span className={clsx('text-[10px] font-mono', getTextColor(zScore))}>
                          {metric.value >= 1000
                            ? `${(metric.value / 1000).toFixed(1)}k`
                            : metric.value.toFixed(1)}
                        </span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 pt-3 border-t border-slate-700/50">
        <span className="text-[10px] text-slate-500">z-score:</span>
        <div className="flex items-center gap-1">
          <div className="w-4 h-3 bg-green-500/40 rounded" />
          <span className="text-[10px] text-slate-500">&lt;2</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-3 bg-yellow-500/50 rounded" />
          <span className="text-[10px] text-slate-500">2-3</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-3 bg-red-500/70 rounded" />
          <span className="text-[10px] text-slate-500">&gt;3</span>
        </div>
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div
          className="fixed z-50 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-xs shadow-xl pointer-events-none"
          style={{
            left: tooltip.x,
            top: tooltip.y - 60,
            transform: 'translateX(-50%)',
          }}
        >
          <div className="font-medium text-slate-200">{tooltip.metric}</div>
          <div className="text-slate-400">Value: {tooltip.value.toFixed(4)}</div>
          <div className={getTextColor(tooltip.zScore)}>
            Z-Score: {tooltip.zScore.toFixed(2)}
          </div>
        </div>
      )}
    </div>
  )
}
