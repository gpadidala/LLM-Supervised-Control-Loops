import { useEffect, useState } from 'react'
import { useSCLStore } from '@/store/scl.store'
import RegimeBadge from '@/components/RegimeBadge'
import ConfidenceGauge from '@/components/ConfidenceGauge'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from 'recharts'
import { format } from 'date-fns'
import {
  ChevronDown,
  ChevronRight,
  Shield,
  Send,
  AlertTriangle,
} from 'lucide-react'
import clsx from 'clsx'
import type { Decision, AutonomyLevel } from '@/types'
import { api } from '@/api/client'

const autonomyColors: Record<AutonomyLevel, string> = {
  execute_autonomous: '#22c55e',
  execute_with_notification: '#3b82f6',
  recommend: '#eab308',
  escalate: '#ef4444',
}

const autonomyLabels: Record<AutonomyLevel, string> = {
  execute_autonomous: 'Autonomous',
  execute_with_notification: 'Notify',
  recommend: 'Recommend',
  escalate: 'Escalate',
}

export default function Decisions() {
  const { decisions, fetchDecisions, cycles } = useSCLStore()
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [overrideOpen, setOverrideOpen] = useState(false)
  const [overrideAction, setOverrideAction] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    fetchDecisions()
  }, [fetchDecisions])

  // Derive decisions from cycles if decisions endpoint is empty
  const allDecisions: Decision[] =
    decisions.length > 0
      ? decisions
      : cycles
          .filter((c) => c.decision)
          .map((c) => ({
            cycle_id: c.cycle_id,
            timestamp: c.timestamp,
            selected_action: c.decision.selected_action || {
              id: '',
              type: 'noop',
              description: 'No action',
              parameters: {},
              target_service: null,
              blast_radius: 0,
              reversibility: 1,
              estimated_cost_delta: 0,
            },
            reasoning: c.decision.reasoning || '',
            confidence: c.decision.confidence || 0,
            autonomy_level: c.decision.autonomy_level || 'recommend',
            alternative_actions: c.decision.alternative_actions || [],
            rollback_plan: c.decision.rollback_plan || '',
            rollback_trigger: c.decision.rollback_trigger || '',
          }))

  // Autonomy level pie chart data
  const autonomyCounts: Record<string, number> = {}
  allDecisions.forEach((d) => {
    const level = d.autonomy_level || 'recommend'
    autonomyCounts[level] = (autonomyCounts[level] || 0) + 1
  })
  const pieData = Object.entries(autonomyCounts).map(([key, count]) => ({
    name: autonomyLabels[key as AutonomyLevel] || key,
    value: count,
    color: autonomyColors[key as AutonomyLevel] || '#64748b',
  }))

  // Confidence distribution histogram
  const confidenceBuckets = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
  const histData = confidenceBuckets.slice(0, -1).map((low, i) => {
    const high = confidenceBuckets[i + 1]
    const count = allDecisions.filter(
      (d) => d.confidence >= low && d.confidence < high
    ).length
    return {
      range: `${(low * 100).toFixed(0)}-${(high * 100).toFixed(0)}%`,
      count,
    }
  })

  const handleOverride = async () => {
    if (!overrideAction.trim()) return
    setSubmitting(true)
    try {
      await api.decisions.override({
        action: overrideAction,
        reason: overrideReason,
      })
      setOverrideOpen(false)
      setOverrideAction('')
      setOverrideReason('')
      fetchDecisions()
    } catch (err) {
      console.error('Override failed:', err)
    }
    setSubmitting(false)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Decisions</h2>
          <p className="text-sm text-slate-400 mt-1">
            Decision audit log and human override interface
          </p>
        </div>
        <button
          onClick={() => setOverrideOpen(!overrideOpen)}
          className="btn-primary flex items-center gap-2"
        >
          <Shield className="w-4 h-4" />
          Human Override
        </button>
      </div>

      {/* Override Form */}
      {overrideOpen && (
        <div className="card border-amber-500/30">
          <div className="card-header flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            Human Override
          </div>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">
                Override Action
              </label>
              <input
                type="text"
                value={overrideAction}
                onChange={(e) => setOverrideAction(e.target.value)}
                placeholder="e.g., scale_up api-service to 5 replicas"
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">
                Reason
              </label>
              <textarea
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Explain why this override is needed..."
                rows={3}
                className="w-full px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-blue-500 resize-none"
              />
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleOverride}
                disabled={submitting || !overrideAction.trim()}
                className="btn-primary flex items-center gap-2"
              >
                <Send className="w-4 h-4" />
                Submit Override
              </button>
              <button
                onClick={() => setOverrideOpen(false)}
                className="btn-secondary"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stats Row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Autonomy Level Pie */}
        <div className="card">
          <div className="card-header">Autonomy Level Distribution</div>
          {pieData.length > 0 ? (
            <div className="flex items-center">
              <ResponsiveContainer width="50%" height={200}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    dataKey="value"
                    strokeWidth={0}
                  >
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e293b',
                      border: '1px solid #475569',
                      borderRadius: '8px',
                      fontSize: '12px',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 ml-4">
                {pieData.map((d) => (
                  <div key={d.name} className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: d.color }}
                    />
                    <span className="text-xs text-slate-400">
                      {d.name}: {d.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="h-[200px] flex items-center justify-center text-sm text-slate-500">
              No decision data
            </div>
          )}
        </div>

        {/* Confidence Distribution */}
        <div className="card">
          <div className="card-header">Confidence Distribution</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={histData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="range" stroke="#64748b" fontSize={10} />
              <YAxis stroke="#64748b" fontSize={10} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Decision Table */}
      <div className="card">
        <div className="card-header">Recent Decisions ({allDecisions.length})</div>
        {allDecisions.length > 0 ? (
          <div className="space-y-1">
            {allDecisions.map((d) => {
              const isExpanded = expandedId === d.cycle_id
              return (
                <div key={d.cycle_id} className="border border-slate-700/30 rounded-lg overflow-hidden">
                  {/* Row */}
                  <button
                    onClick={() =>
                      setExpandedId(isExpanded ? null : d.cycle_id)
                    }
                    className="w-full flex items-center gap-4 px-4 py-3 hover:bg-slate-800/50 transition-colors text-left"
                  >
                    {isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-slate-500" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-slate-500" />
                    )}
                    <span className="text-xs text-slate-500 font-mono w-24 flex-shrink-0">
                      {(() => {
                        try {
                          return format(new Date(d.timestamp), 'HH:mm:ss')
                        } catch {
                          return d.timestamp?.slice(0, 19) || 'N/A'
                        }
                      })()}
                    </span>
                    <span className="text-sm text-slate-300 flex-1 truncate">
                      {d.selected_action?.description || 'No action'}
                    </span>
                    <span
                      className={clsx(
                        'text-xs font-mono w-14 text-right',
                        d.confidence >= 0.8
                          ? 'text-green-400'
                          : d.confidence >= 0.6
                          ? 'text-yellow-400'
                          : 'text-red-400'
                      )}
                    >
                      {(d.confidence * 100).toFixed(0)}%
                    </span>
                    <span
                      className="text-[10px] px-2 py-0.5 rounded-full font-medium"
                      style={{
                        backgroundColor: `${
                          autonomyColors[d.autonomy_level] || '#64748b'
                        }20`,
                        color: autonomyColors[d.autonomy_level] || '#64748b',
                      }}
                    >
                      {autonomyLabels[d.autonomy_level] || d.autonomy_level}
                    </span>
                  </button>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className="px-4 py-4 bg-slate-800/30 border-t border-slate-700/30 space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <span className="text-xs text-slate-500 block mb-1">
                            Reasoning
                          </span>
                          <p className="text-sm text-slate-300 leading-relaxed">
                            {d.reasoning || 'No reasoning provided'}
                          </p>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500 block mb-1">
                            Rollback Plan
                          </span>
                          <p className="text-sm text-slate-300 leading-relaxed">
                            {d.rollback_plan || 'No rollback plan'}
                          </p>
                        </div>
                      </div>
                      {d.rollback_trigger && (
                        <div>
                          <span className="text-xs text-slate-500 block mb-1">
                            Rollback Trigger
                          </span>
                          <p className="text-sm text-slate-300">
                            {d.rollback_trigger}
                          </p>
                        </div>
                      )}
                      <div className="flex items-center gap-4 pt-2 border-t border-slate-700/30">
                        <div>
                          <span className="text-xs text-slate-500">Type</span>
                          <p className="text-sm text-slate-300">
                            {d.selected_action?.type?.replace(/_/g, ' ') || 'N/A'}
                          </p>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">
                            Blast Radius
                          </span>
                          <p className="text-sm text-slate-300">
                            {((d.selected_action?.blast_radius || 0) * 100).toFixed(0)}%
                          </p>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">
                            Reversibility
                          </span>
                          <p className="text-sm text-slate-300">
                            {((d.selected_action?.reversibility || 0) * 100).toFixed(0)}%
                          </p>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">
                            Cost Delta
                          </span>
                          <p className="text-sm text-slate-300">
                            ${(d.selected_action?.estimated_cost_delta || 0).toFixed(2)}/hr
                          </p>
                        </div>
                        <div>
                          <span className="text-xs text-slate-500">
                            Alternatives
                          </span>
                          <p className="text-sm text-slate-300">
                            {d.alternative_actions?.length || 0}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        ) : (
          <div className="h-32 flex items-center justify-center text-sm text-slate-500">
            No decisions recorded yet. Start the governor to generate decisions.
          </div>
        )}
      </div>
    </div>
  )
}
