import clsx from 'clsx'
import type { ActionCandidate } from '@/types'
import { Target, RotateCcw, DollarSign } from 'lucide-react'

interface ActionCardProps {
  action: ActionCandidate
  selected?: boolean
  onClick?: () => void
}

const typeColors: Record<string, string> = {
  scale_up: 'bg-blue-500/20 text-blue-400 ring-blue-500/30',
  scale_down: 'bg-cyan-500/20 text-cyan-400 ring-cyan-500/30',
  restart: 'bg-orange-500/20 text-orange-400 ring-orange-500/30',
  failover: 'bg-red-500/20 text-red-400 ring-red-500/30',
  optimize: 'bg-green-500/20 text-green-400 ring-green-500/30',
  migrate: 'bg-purple-500/20 text-purple-400 ring-purple-500/30',
  noop: 'bg-slate-500/20 text-slate-400 ring-slate-500/30',
  throttle: 'bg-yellow-500/20 text-yellow-400 ring-yellow-500/30',
  cache_flush: 'bg-teal-500/20 text-teal-400 ring-teal-500/30',
}

function getTypeColor(type: string): string {
  return typeColors[type] || 'bg-slate-500/20 text-slate-400 ring-slate-500/30'
}

export default function ActionCard({ action, selected, onClick }: ActionCardProps) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'card cursor-pointer transition-all duration-200 hover:border-slate-600',
        selected && 'border-blue-500/50 ring-1 ring-blue-500/20 bg-blue-500/5'
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <span
          className={clsx(
            'px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ring-1',
            getTypeColor(action.type)
          )}
        >
          {action.type.replace(/_/g, ' ')}
        </span>
        {selected && (
          <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-blue-500/20 text-blue-400">
            Selected
          </span>
        )}
      </div>

      <p className="text-sm text-slate-200 mb-3 line-clamp-2">
        {action.description}
      </p>

      {action.target_service && (
        <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-3">
          <Target className="w-3 h-3" />
          <span>{action.target_service}</span>
        </div>
      )}

      <div className="space-y-2">
        {/* Blast Radius */}
        <div>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-slate-500">Blast Radius</span>
            <span className="text-slate-400">{(action.blast_radius * 100).toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all',
                action.blast_radius > 0.7
                  ? 'bg-red-500'
                  : action.blast_radius > 0.4
                  ? 'bg-yellow-500'
                  : 'bg-green-500'
              )}
              style={{ width: `${action.blast_radius * 100}%` }}
            />
          </div>
        </div>

        {/* Reversibility */}
        <div>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-slate-500">
              <RotateCcw className="w-3 h-3 inline mr-1" />
              Reversibility
            </span>
            <span className="text-slate-400">{(action.reversibility * 100).toFixed(0)}%</span>
          </div>
          <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={clsx(
                'h-full rounded-full transition-all',
                action.reversibility > 0.7
                  ? 'bg-green-500'
                  : action.reversibility > 0.4
                  ? 'bg-yellow-500'
                  : 'bg-red-500'
              )}
              style={{ width: `${action.reversibility * 100}%` }}
            />
          </div>
        </div>

        {/* Cost Delta */}
        <div className="flex items-center justify-between text-xs pt-1">
          <span className="text-slate-500">
            <DollarSign className="w-3 h-3 inline mr-1" />
            Cost Delta
          </span>
          <span
            className={clsx(
              'font-medium',
              action.estimated_cost_delta > 0
                ? 'text-red-400'
                : action.estimated_cost_delta < 0
                ? 'text-green-400'
                : 'text-slate-400'
            )}
          >
            {action.estimated_cost_delta > 0 ? '+' : ''}
            ${action.estimated_cost_delta.toFixed(2)}/hr
          </span>
        </div>
      </div>
    </div>
  )
}
