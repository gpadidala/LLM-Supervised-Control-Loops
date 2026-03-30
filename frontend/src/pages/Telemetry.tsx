import { useEffect, useState } from 'react'
import { useSCLStore } from '@/store/scl.store'
import MetricChart from '@/components/MetricChart'
import StateTensor from '@/components/StateTensor'
import clsx from 'clsx'
import { AlertTriangle, ArrowDown, ArrowUp, Minus } from 'lucide-react'
import type { TelemetryVector, TrendVector } from '@/types'

const signalClasses = [
  { key: 'infrastructure', label: 'Infrastructure', color: '#3b82f6' },
  { key: 'application', label: 'Application', color: '#22c55e' },
  { key: 'business', label: 'Business', color: '#eab308' },
  { key: 'network', label: 'Network', color: '#a855f7' },
  { key: 'cost', label: 'Cost', color: '#ef4444' },
] as const

type SignalKey = (typeof signalClasses)[number]['key']

export default function Telemetry() {
  const { currentState, fetchTelemetry, fetchAnomalies, anomalies } = useSCLStore()
  const [activeTab, setActiveTab] = useState<SignalKey>('infrastructure')
  const [viewMode, setViewMode] = useState<'charts' | 'tensor'>('charts')

  useEffect(() => {
    fetchTelemetry()
    fetchAnomalies()
    const interval = setInterval(() => {
      fetchTelemetry()
    }, 5000)
    return () => clearInterval(interval)
  }, [fetchTelemetry, fetchAnomalies])

  const currentVector: TelemetryVector | undefined = currentState
    ? (currentState as any)[activeTab]
    : undefined

  const activeColor = signalClasses.find((s) => s.key === activeTab)?.color || '#3b82f6'

  // Build chart data from current metrics (single point per metric for now; real app would use history)
  const metricsData = currentVector?.metrics?.map((m) => ({
    name: m.name,
    data: [
      {
        timestamp: m.timestamp || currentState?.timestamp || new Date().toISOString(),
        value: m.value,
      },
    ],
    unit: m.unit,
    isAnomalous:
      anomalies.find((a) => a.metric_name === m.name)?.is_anomalous || false,
    zScore: anomalies.find((a) => a.metric_name === m.name)?.z_score || 0,
  })) || []

  const trendVectors: TrendVector[] = currentState?.derived?.trend_vectors || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Telemetry</h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time metrics across all signal classes
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewMode('charts')}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
              viewMode === 'charts' ? 'tab-active' : 'tab-inactive'
            )}
          >
            Charts
          </button>
          <button
            onClick={() => setViewMode('tensor')}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-sm font-medium transition-all',
              viewMode === 'tensor' ? 'tab-active' : 'tab-inactive'
            )}
          >
            Tensor View
          </button>
        </div>
      </div>

      {/* Signal Class Tabs */}
      <div className="flex items-center gap-1 bg-slate-800/50 p-1 rounded-xl border border-slate-700/50">
        {signalClasses.map((sc) => (
          <button
            key={sc.key}
            onClick={() => setActiveTab(sc.key)}
            className={clsx(
              'flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all',
              activeTab === sc.key ? 'tab-active' : 'tab-inactive'
            )}
          >
            <span
              className="inline-block w-2 h-2 rounded-full mr-2"
              style={{
                backgroundColor: sc.color,
                opacity: activeTab === sc.key ? 1 : 0.4,
              }}
            />
            {sc.label}
          </button>
        ))}
      </div>

      {viewMode === 'charts' ? (
        <>
          {/* Metric Charts Grid */}
          {metricsData.length > 0 ? (
            <div className="grid grid-cols-2 gap-4">
              {metricsData.map((metric) => (
                <div key={metric.name} className="relative">
                  {metric.isAnomalous && (
                    <div className="absolute top-2 right-2 z-10 flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 text-[10px] font-medium">
                      <AlertTriangle className="w-3 h-3" />
                      Anomaly (z={metric.zScore.toFixed(1)})
                    </div>
                  )}
                  <MetricChart
                    title={`${metric.name} ${metric.unit ? `(${metric.unit})` : ''}`}
                    data={metric.data}
                    color={activeColor}
                    height={180}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="card h-48 flex items-center justify-center text-slate-500">
              No metrics available for {activeTab}. Start the governor to collect telemetry.
            </div>
          )}

          {/* Trend Vectors Table */}
          <div className="card">
            <div className="card-header">Trend Vectors</div>
            {trendVectors.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-500 text-xs uppercase">
                      <th className="text-left pb-3 font-medium">Metric</th>
                      <th className="text-right pb-3 font-medium">5min Delta</th>
                      <th className="text-right pb-3 font-medium">15min Delta</th>
                      <th className="text-right pb-3 font-medium">1hr Delta</th>
                      <th className="text-center pb-3 font-medium">Trend</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    {trendVectors.map((tv) => {
                      const mainDelta = tv.delta_5min
                      return (
                        <tr key={tv.metric_name} className="hover:bg-slate-800/30">
                          <td className="py-2.5 text-slate-300">{tv.metric_name}</td>
                          <td className="py-2.5 text-right">
                            <DeltaValue value={tv.delta_5min} />
                          </td>
                          <td className="py-2.5 text-right">
                            <DeltaValue value={tv.delta_15min} />
                          </td>
                          <td className="py-2.5 text-right">
                            <DeltaValue value={tv.delta_1hr} />
                          </td>
                          <td className="py-2.5 text-center">
                            {mainDelta > 0.01 ? (
                              <ArrowUp className="w-4 h-4 text-red-400 inline" />
                            ) : mainDelta < -0.01 ? (
                              <ArrowDown className="w-4 h-4 text-green-400 inline" />
                            ) : (
                              <Minus className="w-4 h-4 text-slate-500 inline" />
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="h-24 flex items-center justify-center text-sm text-slate-500">
                No trend data available
              </div>
            )}
          </div>
        </>
      ) : (
        /* Tensor View */
        <StateTensor state={currentState} />
      )}
    </div>
  )
}

function DeltaValue({ value }: { value: number }) {
  if (value === 0 || value === undefined)
    return <span className="text-slate-500 font-mono text-xs">0.00</span>
  return (
    <span
      className={clsx(
        'font-mono text-xs',
        value > 0 ? 'text-red-400' : 'text-green-400'
      )}
    >
      {value > 0 ? '+' : ''}
      {value.toFixed(4)}
    </span>
  )
}
