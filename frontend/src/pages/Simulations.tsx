import { useEffect, useState } from 'react'
import { useSCLStore } from '@/store/scl.store'
import ActionCard from '@/components/ActionCard'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts'
import { Target, TrendingUp, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'
import type { SimulationResult, ActionCandidate } from '@/types'

export default function Simulations() {
  const { simulations, fetchSimulations, latestCycle } = useSCLStore()
  const [selectedAction, setSelectedAction] = useState<string | null>(null)

  useEffect(() => {
    fetchSimulations()
  }, [fetchSimulations])

  // Extract actions from latest cycle if available
  const actions: ActionCandidate[] = latestCycle?.decision?.alternative_actions || []
  const selectedActionFromDecision = latestCycle?.decision?.selected_action

  // Pareto scatter data
  const scatterData = simulations.map((s) => ({
    x: s.expected_cost_delta,
    y: s.expected_objective,
    z: (1 - s.sla_breach_probability) * 100,
    name: s.action_description,
    isPareto: s.is_pareto_optimal,
    id: s.action_id,
  }))

  // Comparison bar data
  const comparisonData = simulations.map((s) => ({
    name: s.action_description?.length > 20
      ? s.action_description.slice(0, 20) + '...'
      : s.action_description || s.action_id.slice(0, 8),
    objective: s.expected_objective,
    sla: (1 - s.sla_breach_probability) * 100,
    cost: s.expected_cost_delta,
    cvar: s.cvar_alpha,
    isPareto: s.is_pareto_optimal,
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white">Simulations</h2>
        <p className="text-sm text-slate-400 mt-1">
          Monte Carlo simulations and Pareto-optimal action selection
        </p>
      </div>

      {/* Pareto Frontier Scatter Plot */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Target className="w-3.5 h-3.5 text-blue-400" />
          Pareto Frontier (Cost vs Performance)
        </div>
        {scatterData.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                type="number"
                dataKey="x"
                name="Cost Delta"
                stroke="#64748b"
                fontSize={11}
                label={{
                  value: 'Cost Delta ($/hr)',
                  position: 'bottom',
                  fill: '#94a3b8',
                  fontSize: 11,
                }}
              />
              <YAxis
                type="number"
                dataKey="y"
                name="Expected Objective"
                stroke="#64748b"
                fontSize={11}
                label={{
                  value: 'Expected Objective',
                  angle: -90,
                  position: 'insideLeft',
                  fill: '#94a3b8',
                  fontSize: 11,
                }}
              />
              <ZAxis type="number" dataKey="z" range={[50, 400]} name="SLA Compliance %" />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
                formatter={(value: number, name: string) => [
                  name === 'Cost Delta'
                    ? `$${value.toFixed(2)}/hr`
                    : name === 'SLA Compliance %'
                    ? `${value.toFixed(1)}%`
                    : value.toFixed(4),
                  name,
                ]}
              />
              {/* Non-Pareto points */}
              <Scatter
                name="Non-Pareto"
                data={scatterData.filter((d) => !d.isPareto)}
                fill="#64748b"
                fillOpacity={0.5}
              />
              {/* Pareto-optimal points */}
              <Scatter
                name="Pareto Optimal"
                data={scatterData.filter((d) => d.isPareto)}
                fill="#22c55e"
                fillOpacity={0.9}
                shape="star"
              />
            </ScatterChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[350px] flex items-center justify-center text-slate-500">
            No simulation data available. Run a control cycle to generate simulations.
          </div>
        )}
      </div>

      {/* Action Cards (top candidates) */}
      {(actions.length > 0 || selectedActionFromDecision) && (
        <div>
          <h3 className="text-sm font-medium text-slate-400 uppercase tracking-wider mb-3">
            Action Candidates
          </h3>
          <div className="grid grid-cols-3 gap-4">
            {selectedActionFromDecision && (
              <ActionCard action={selectedActionFromDecision} selected />
            )}
            {actions.slice(0, selectedActionFromDecision ? 2 : 3).map((a: ActionCandidate) => (
              <ActionCard
                key={a.id}
                action={a}
                selected={selectedAction === a.id}
                onClick={() => setSelectedAction(a.id === selectedAction ? null : a.id)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Comparison Table */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-green-400" />
          Simulation Comparison
        </div>
        {simulations.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-500 text-xs uppercase">
                  <th className="text-left pb-3 font-medium">Action</th>
                  <th className="text-right pb-3 font-medium">Scenarios</th>
                  <th className="text-right pb-3 font-medium">Expected Obj.</th>
                  <th className="text-right pb-3 font-medium">VaR</th>
                  <th className="text-right pb-3 font-medium">CVaR</th>
                  <th className="text-right pb-3 font-medium">SLA Breach %</th>
                  <th className="text-right pb-3 font-medium">Cost Delta</th>
                  <th className="text-center pb-3 font-medium">Pareto</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {simulations.map((sim) => (
                  <tr
                    key={sim.action_id}
                    className={clsx(
                      'hover:bg-slate-800/30 transition-colors',
                      sim.is_pareto_optimal && 'bg-green-500/5'
                    )}
                  >
                    <td className="py-2.5 text-slate-300 max-w-[200px] truncate">
                      {sim.action_description || sim.action_id.slice(0, 12)}
                    </td>
                    <td className="py-2.5 text-right text-slate-400 font-mono text-xs">
                      {sim.n_scenarios.toLocaleString()}
                    </td>
                    <td className="py-2.5 text-right text-slate-300 font-mono text-xs">
                      {sim.expected_objective.toFixed(4)}
                    </td>
                    <td className="py-2.5 text-right text-slate-400 font-mono text-xs">
                      {sim.var_alpha.toFixed(4)}
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs">
                      <span
                        className={
                          sim.cvar_alpha < -0.1 ? 'text-red-400' : 'text-slate-400'
                        }
                      >
                        {sim.cvar_alpha.toFixed(4)}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs">
                      <span
                        className={clsx(
                          sim.sla_breach_probability > 0.2
                            ? 'text-red-400'
                            : sim.sla_breach_probability > 0.05
                            ? 'text-yellow-400'
                            : 'text-green-400'
                        )}
                      >
                        {(sim.sla_breach_probability * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-mono text-xs">
                      <span
                        className={clsx(
                          sim.expected_cost_delta > 0 ? 'text-red-400' : 'text-green-400'
                        )}
                      >
                        {sim.expected_cost_delta > 0 ? '+' : ''}$
                        {sim.expected_cost_delta.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5 text-center">
                      {sim.is_pareto_optimal ? (
                        <span className="text-green-400 text-xs font-medium">Yes</span>
                      ) : (
                        <span className="text-slate-600 text-xs">No</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="h-24 flex items-center justify-center text-sm text-slate-500">
            No simulation results to compare
          </div>
        )}
      </div>

      {/* Scenario Distribution */}
      {simulations.length > 0 && (
        <div className="card">
          <div className="card-header">Expected Objective Distribution</div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={comparisonData} margin={{ top: 10, right: 30, bottom: 40, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis
                dataKey="name"
                stroke="#64748b"
                fontSize={10}
                angle={-30}
                textAnchor="end"
                height={60}
              />
              <YAxis stroke="#64748b" fontSize={10} />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #475569',
                  borderRadius: '8px',
                  fontSize: '12px',
                }}
              />
              <Bar dataKey="objective" name="Expected Objective" radius={[4, 4, 0, 0]}>
                {comparisonData.map((entry, index) => (
                  <Cell
                    key={index}
                    fill={entry.isPareto ? '#22c55e' : '#3b82f6'}
                    fillOpacity={0.8}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
