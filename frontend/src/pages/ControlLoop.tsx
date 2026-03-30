import { useEffect, useState } from 'react'
import { useSCLStore } from '@/store/scl.store'
import CycleTimeline from '@/components/CycleTimeline'
import RegimeBadge from '@/components/RegimeBadge'
import { format } from 'date-fns'
import { ChevronDown, Code, Eye } from 'lucide-react'
import clsx from 'clsx'
import type { ControlCycleOutput } from '@/types'

type PhaseKey = 'observe' | 'predict' | 'simulate' | 'decide' | 'actuate' | 'learn'

export default function ControlLoop() {
  const { cycles, latestCycle, fetchCycles } = useSCLStore()
  const [selectedCycleId, setSelectedCycleId] = useState<string | null>(null)
  const [showJson, setShowJson] = useState(false)
  const [activePhase, setActivePhase] = useState<PhaseKey>('observe')
  const [dropdownOpen, setDropdownOpen] = useState(false)

  useEffect(() => {
    fetchCycles()
  }, [fetchCycles])

  const selectedCycle = selectedCycleId
    ? cycles.find((c) => c.cycle_id === selectedCycleId) || latestCycle
    : latestCycle

  const phases = selectedCycle
    ? [
        { name: 'Observe', status: 'complete' as const },
        { name: 'Predict', status: selectedCycle.prediction ? ('complete' as const) : ('pending' as const) },
        { name: 'Simulate', status: selectedCycle.simulation_results ? ('complete' as const) : ('pending' as const) },
        { name: 'Decide', status: selectedCycle.decision ? ('complete' as const) : ('pending' as const) },
        {
          name: 'Actuate',
          status:
            selectedCycle.execution_status === 'executed'
              ? ('complete' as const)
              : selectedCycle.execution_status === 'failed'
              ? ('error' as const)
              : ('pending' as const),
        },
        { name: 'Learn', status: selectedCycle.learning_update ? ('complete' as const) : ('pending' as const) },
      ]
    : undefined

  const phaseData: Record<PhaseKey, any> = selectedCycle
    ? {
        observe: {
          state_summary: selectedCycle.state_summary,
          regime: selectedCycle.system_regime,
        },
        predict: selectedCycle.prediction,
        simulate: selectedCycle.simulation_results,
        decide: selectedCycle.decision,
        actuate: {
          execution_status: selectedCycle.execution_status,
          cycle_id: selectedCycle.cycle_id,
        },
        learn: selectedCycle.learning_update,
      }
    : {
        observe: null,
        predict: null,
        simulate: null,
        decide: null,
        actuate: null,
        learn: null,
      }

  const phaseLabels: Record<PhaseKey, string> = {
    observe: 'Observe',
    predict: 'Predict',
    simulate: 'Simulate',
    decide: 'Decide',
    actuate: 'Actuate',
    learn: 'Learn',
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Control Loop</h2>
          <p className="text-sm text-slate-400 mt-1">
            Detailed view of the OODA-inspired control cycle
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Cycle Selector */}
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="btn-secondary flex items-center gap-2 min-w-[240px] justify-between"
            >
              <span className="text-sm truncate">
                {selectedCycle
                  ? `Cycle ${selectedCycle.cycle_id.slice(0, 8)}...`
                  : 'Select Cycle'}
              </span>
              <ChevronDown className="w-4 h-4" />
            </button>
            {dropdownOpen && (
              <div className="absolute right-0 top-full mt-1 w-80 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-64 overflow-y-auto">
                {cycles.map((c) => (
                  <button
                    key={c.cycle_id}
                    onClick={() => {
                      setSelectedCycleId(c.cycle_id)
                      setDropdownOpen(false)
                    }}
                    className={clsx(
                      'w-full text-left px-3 py-2 text-sm hover:bg-slate-700 flex items-center justify-between',
                      c.cycle_id === selectedCycle?.cycle_id && 'bg-slate-700/50'
                    )}
                  >
                    <span className="font-mono text-xs text-slate-300 truncate">
                      {c.cycle_id.slice(0, 12)}
                    </span>
                    <div className="flex items-center gap-2">
                      <RegimeBadge regime={c.system_regime} size="sm" />
                      <span className="text-[10px] text-slate-500">
                        {(() => {
                          try {
                            return format(new Date(c.timestamp), 'HH:mm:ss')
                          } catch {
                            return ''
                          }
                        })()}
                      </span>
                    </div>
                  </button>
                ))}
                {cycles.length === 0 && (
                  <div className="px-3 py-4 text-sm text-slate-500 text-center">
                    No cycles available
                  </div>
                )}
              </div>
            )}
          </div>

          {/* JSON toggle */}
          <button
            onClick={() => setShowJson(!showJson)}
            className={clsx(
              'btn-secondary flex items-center gap-2',
              showJson && 'bg-slate-600'
            )}
          >
            {showJson ? <Eye className="w-4 h-4" /> : <Code className="w-4 h-4" />}
            {showJson ? 'Visual' : 'JSON'}
          </button>
        </div>
      </div>

      {/* Large CycleTimeline */}
      <div className="card">
        <div className="card-header">Pipeline Phases</div>
        <div className="py-6 px-4">
          <CycleTimeline phases={phases} />
        </div>
        {selectedCycle && (
          <div className="flex items-center justify-between text-xs text-slate-500 pt-3 border-t border-slate-700/50">
            <span>Cycle: {selectedCycle.cycle_id}</span>
            <span>
              {(() => {
                try {
                  return format(new Date(selectedCycle.timestamp), 'PPpp')
                } catch {
                  return selectedCycle.timestamp
                }
              })()}
            </span>
          </div>
        )}
      </div>

      {/* Phase Details */}
      {showJson ? (
        <div className="card">
          <div className="card-header">Raw Cycle Output</div>
          <pre className="text-xs text-slate-300 bg-slate-900 rounded-lg p-4 overflow-auto max-h-[500px] font-mono">
            {JSON.stringify(selectedCycle, null, 2)}
          </pre>
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-4">
          {/* Phase tabs */}
          <div className="space-y-1">
            {(Object.keys(phaseLabels) as PhaseKey[]).map((key) => (
              <button
                key={key}
                onClick={() => setActivePhase(key)}
                className={clsx(
                  'w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                  activePhase === key
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/20'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                )}
              >
                {phaseLabels[key]}
              </button>
            ))}
          </div>

          {/* Phase content */}
          <div className="col-span-3 card">
            <div className="card-header">{phaseLabels[activePhase]} Phase Output</div>
            {phaseData[activePhase] ? (
              <div className="space-y-3">
                {activePhase === 'observe' && selectedCycle && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-slate-400">Regime:</span>
                      <RegimeBadge regime={selectedCycle.system_regime} />
                    </div>
                    <div>
                      <span className="text-sm text-slate-400">Anomalies Detected:</span>
                      <span className="ml-2 text-sm text-slate-200">
                        {selectedCycle.state_summary?.anomalies_detected ?? 0}
                      </span>
                    </div>
                    <div>
                      <span className="text-sm text-slate-400">Top Concerns:</span>
                      <ul className="mt-1 space-y-1">
                        {(selectedCycle.state_summary?.top_concerns ?? []).map(
                          (c: string, i: number) => (
                            <li key={i} className="text-sm text-slate-300 flex items-start gap-2">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 mt-1.5 flex-shrink-0" />
                              {c}
                            </li>
                          )
                        )}
                      </ul>
                    </div>
                  </div>
                )}

                {activePhase === 'decide' && selectedCycle?.decision && (
                  <div className="space-y-3">
                    <div>
                      <span className="text-sm text-slate-400">Action:</span>
                      <p className="text-sm text-slate-200 mt-1">
                        {selectedCycle.decision.selected_action?.description || 'N/A'}
                      </p>
                    </div>
                    <div>
                      <span className="text-sm text-slate-400">Reasoning:</span>
                      <p className="text-sm text-slate-300 mt-1">
                        {selectedCycle.decision.reasoning || 'N/A'}
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div>
                        <span className="text-xs text-slate-500">Confidence</span>
                        <p className="text-sm font-medium text-slate-200">
                          {((selectedCycle.decision.confidence || 0) * 100).toFixed(1)}%
                        </p>
                      </div>
                      <div>
                        <span className="text-xs text-slate-500">Autonomy</span>
                        <p className="text-sm font-medium text-slate-200">
                          {selectedCycle.decision.autonomy_level?.replace(/_/g, ' ') || 'N/A'}
                        </p>
                      </div>
                    </div>
                    {selectedCycle.decision.rollback_plan && (
                      <div>
                        <span className="text-sm text-slate-400">Rollback Plan:</span>
                        <p className="text-sm text-slate-300 mt-1">
                          {selectedCycle.decision.rollback_plan}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {activePhase !== 'observe' && activePhase !== 'decide' && (
                  <pre className="text-xs text-slate-300 bg-slate-900 rounded-lg p-4 overflow-auto max-h-[400px] font-mono">
                    {JSON.stringify(phaseData[activePhase], null, 2)}
                  </pre>
                )}
              </div>
            ) : (
              <div className="h-32 flex items-center justify-center text-sm text-slate-500">
                No data for this phase
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
