import { useEffect } from 'react'
import { useSCLStore } from '@/store/scl.store'
import RegimeBadge from '@/components/RegimeBadge'
import CycleTimeline from '@/components/CycleTimeline'
import ConfidenceGauge from '@/components/ConfidenceGauge'
import {
  LineChart,
  Line,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import {
  Play,
  Square,
  RotateCw,
  Shield,
  Activity,
  AlertTriangle,
  Clock,
  Zap,
} from 'lucide-react'
import { format } from 'date-fns'
import clsx from 'clsx'
import type { Regime } from '@/types'

const regimeColorMap: Record<Regime, string> = {
  normal: '#22c55e',
  degraded: '#eab308',
  critical: '#ef4444',
  recovery: '#3b82f6',
  maintenance: '#a855f7',
}

export default function Dashboard() {
  const {
    status,
    latestCycle,
    cycles,
    loading,
    startGovernor,
    stopGovernor,
    triggerCycle,
    fetchCycles,
    fetchAnomalies,
    anomalies,
  } = useSCLStore()

  useEffect(() => {
    fetchCycles()
    fetchAnomalies()
  }, [fetchCycles, fetchAnomalies])

  const confidence = latestCycle?.decision?.confidence ?? 0
  const slaEta = latestCycle?.state_summary?.sla_breach_eta_minutes
  const anomalyCount = latestCycle?.state_summary?.anomalies_detected ?? 0
  const topConcerns = latestCycle?.state_summary?.top_concerns ?? []

  // Regime timeline data
  const regimeTimeline = cycles
    .slice(0, 50)
    .reverse()
    .map((c, i) => ({
      idx: i,
      regime: c.system_regime,
      cycle_id: c.cycle_id,
      timestamp: c.timestamp,
    }))

  // Derive phases for the latest cycle
  const latestPhases = latestCycle
    ? [
        { name: 'Observe', status: 'complete' as const },
        { name: 'Predict', status: latestCycle.prediction ? 'complete' as const : 'pending' as const },
        { name: 'Simulate', status: latestCycle.simulation_results ? 'complete' as const : 'pending' as const },
        { name: 'Decide', status: latestCycle.decision ? 'complete' as const : 'pending' as const },
        {
          name: 'Actuate',
          status:
            latestCycle.execution_status === 'executed'
              ? ('complete' as const)
              : latestCycle.execution_status === 'failed'
              ? ('error' as const)
              : ('pending' as const),
        },
        { name: 'Learn', status: latestCycle.learning_update ? 'complete' as const : 'pending' as const },
      ]
    : undefined

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Dashboard</h2>
          <p className="text-sm text-slate-400 mt-1">
            Real-time overview of the LLM-Supervised Control Loop
          </p>
        </div>
        <div className="flex items-center gap-3">
          {status?.is_running ? (
            <button
              onClick={stopGovernor}
              disabled={loading}
              className="btn-danger flex items-center gap-2"
            >
              <Square className="w-4 h-4" />
              Stop Governor
            </button>
          ) : (
            <button
              onClick={startGovernor}
              disabled={loading}
              className="btn-primary flex items-center gap-2"
            >
              <Play className="w-4 h-4" />
              Start Governor
            </button>
          )}
          <button
            onClick={triggerCycle}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
          >
            <RotateCw className={clsx('w-4 h-4', loading && 'animate-spin')} />
            Trigger Cycle
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-4 gap-4">
        {/* Current Regime */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="card-header mb-0">Current Regime</span>
            <Shield className="w-4 h-4 text-slate-500" />
          </div>
          {status ? (
            <RegimeBadge regime={status.current_regime} size="lg" />
          ) : (
            <div className="skeleton h-8 w-24" />
          )}
        </div>

        {/* Cycle Count */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="card-header mb-0">Cycle Count</span>
            <Activity className="w-4 h-4 text-slate-500" />
          </div>
          <div className="stat-value">
            {status ? status.cycle_count.toLocaleString() : <span className="skeleton inline-block h-8 w-16" />}
          </div>
        </div>

        {/* Confidence */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="card-header mb-0">Decision Confidence</span>
            <Zap className="w-4 h-4 text-slate-500" />
          </div>
          <div className="stat-value">
            {latestCycle ? (
              <span
                className={clsx(
                  confidence >= 0.85
                    ? 'text-green-400'
                    : confidence >= 0.65
                    ? 'text-yellow-400'
                    : 'text-red-400'
                )}
              >
                {(confidence * 100).toFixed(1)}%
              </span>
            ) : (
              <span className="skeleton inline-block h-8 w-16" />
            )}
          </div>
        </div>

        {/* SLA Status */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <span className="card-header mb-0">SLA Breach ETA</span>
            <Clock className="w-4 h-4 text-slate-500" />
          </div>
          <div className="stat-value">
            {latestCycle ? (
              slaEta !== null && slaEta !== undefined ? (
                <span
                  className={clsx(
                    slaEta < 15
                      ? 'text-red-400'
                      : slaEta < 60
                      ? 'text-yellow-400'
                      : 'text-green-400'
                  )}
                >
                  {slaEta.toFixed(0)}m
                </span>
              ) : (
                <span className="text-green-400">Safe</span>
              )
            ) : (
              <span className="skeleton inline-block h-8 w-16" />
            )}
          </div>
        </div>
      </div>

      {/* Second Row: Regime Timeline + Sparklines */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card col-span-2">
          <div className="card-header">Regime Timeline (Last 50 Cycles)</div>
          {regimeTimeline.length > 0 ? (
            <div className="flex items-end gap-0.5 h-16">
              {regimeTimeline.map((point, i) => (
                <div
                  key={i}
                  className="flex-1 rounded-sm cursor-pointer transition-all hover:opacity-80 group relative"
                  style={{
                    backgroundColor: regimeColorMap[point.regime] || '#64748b',
                    height: '100%',
                    minWidth: '2px',
                  }}
                  title={`${point.regime} - ${point.cycle_id}`}
                />
              ))}
            </div>
          ) : (
            <div className="h-16 flex items-center justify-center text-sm text-slate-500">
              No cycles recorded yet
            </div>
          )}
          <div className="flex items-center gap-4 mt-3 pt-2 border-t border-slate-700/50">
            {(['normal', 'degraded', 'critical', 'recovery', 'maintenance'] as Regime[]).map(
              (r) => (
                <div key={r} className="flex items-center gap-1.5">
                  <div
                    className="w-2.5 h-2.5 rounded-sm"
                    style={{ backgroundColor: regimeColorMap[r] }}
                  />
                  <span className="text-[10px] text-slate-500 capitalize">{r}</span>
                </div>
              )
            )}
          </div>
        </div>

        {/* Confidence over time sparkline */}
        <div className="card">
          <div className="card-header">Confidence Trend</div>
          {cycles.length > 0 ? (
            <ResponsiveContainer width="100%" height={80}>
              <LineChart
                data={cycles
                  .slice(0, 30)
                  .reverse()
                  .map((c) => ({
                    value: c.decision?.confidence ?? 0,
                    ts: c.timestamp,
                  }))}
              >
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  dot={false}
                />
                <YAxis domain={[0, 1]} hide />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-20 flex items-center justify-center text-sm text-slate-500">
              No data
            </div>
          )}
        </div>
      </div>

      {/* Third Row: Decision Summary + Anomalies */}
      <div className="grid grid-cols-2 gap-4">
        {/* Latest Decision */}
        <div className="card">
          <div className="card-header">Latest Decision</div>
          {latestCycle?.decision ? (
            <div className="space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-sm font-medium text-slate-200">
                    {latestCycle.decision.selected_action?.description || 'No action'}
                  </span>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400">
                      {latestCycle.decision.autonomy_level?.replace(/_/g, ' ') || 'N/A'}
                    </span>
                    <span className="text-xs text-slate-500">
                      {latestCycle.decision.selected_action?.type?.replace(/_/g, ' ') || ''}
                    </span>
                  </div>
                </div>
                <ConfidenceGauge
                  value={latestCycle.decision.confidence || 0}
                  size={80}
                  label=""
                />
              </div>
              {latestCycle.decision.reasoning && (
                <p className="text-xs text-slate-400 leading-relaxed">
                  {latestCycle.decision.reasoning}
                </p>
              )}
            </div>
          ) : (
            <div className="h-24 flex items-center justify-center text-sm text-slate-500">
              No decisions yet
            </div>
          )}
        </div>

        {/* Anomalies & Concerns */}
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            Anomalies & Concerns ({anomalyCount})
          </div>
          {topConcerns.length > 0 ? (
            <ul className="space-y-2">
              {topConcerns.map((concern, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-sm text-slate-300"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 flex-shrink-0" />
                  {concern}
                </li>
              ))}
            </ul>
          ) : anomalies.length > 0 ? (
            <ul className="space-y-2">
              {anomalies
                .filter((a) => a.is_anomalous)
                .slice(0, 5)
                .map((a, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-slate-300">{a.metric_name}</span>
                    <span
                      className={clsx(
                        'text-xs font-mono',
                        Math.abs(a.z_score) > 3
                          ? 'text-red-400'
                          : 'text-yellow-400'
                      )}
                    >
                      z={a.z_score.toFixed(2)}
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <div className="h-24 flex items-center justify-center text-sm text-green-500/70">
              All systems nominal
            </div>
          )}
        </div>
      </div>

      {/* Bottom Row: Cycle Timeline */}
      <div className="card">
        <div className="card-header">Latest Cycle Pipeline</div>
        {latestCycle ? (
          <div className="py-4 px-8">
            <CycleTimeline phases={latestPhases} />
            <div className="mt-3 pt-3 border-t border-slate-700/50 flex items-center justify-between text-xs text-slate-500">
              <span>Cycle: {latestCycle.cycle_id}</span>
              <span>
                {(() => {
                  try {
                    return format(new Date(latestCycle.timestamp), 'PPpp')
                  } catch {
                    return latestCycle.timestamp
                  }
                })()}
              </span>
              <span>
                Status:{' '}
                <span
                  className={clsx(
                    latestCycle.execution_status === 'executed'
                      ? 'text-green-400'
                      : latestCycle.execution_status === 'failed'
                      ? 'text-red-400'
                      : 'text-yellow-400'
                  )}
                >
                  {latestCycle.execution_status || 'pending'}
                </span>
              </span>
            </div>
          </div>
        ) : (
          <div className="h-24 flex items-center justify-center text-sm text-slate-500">
            No cycle data available. Start the governor or trigger a cycle.
          </div>
        )}
      </div>
    </div>
  )
}
