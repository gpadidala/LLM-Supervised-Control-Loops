import clsx from 'clsx'
import {
  Eye,
  TrendingUp,
  FlaskConical,
  Brain,
  Zap,
  GraduationCap,
  CheckCircle2,
  Circle,
  Loader2,
  AlertCircle,
} from 'lucide-react'

type PhaseStatus = 'pending' | 'running' | 'complete' | 'error'

interface Phase {
  name: string
  status: PhaseStatus
  duration?: number // ms
}

interface CycleTimelineProps {
  phases?: Phase[]
  compact?: boolean
}

const phaseDefaults: { name: string; icon: typeof Eye }[] = [
  { name: 'Observe', icon: Eye },
  { name: 'Predict', icon: TrendingUp },
  { name: 'Simulate', icon: FlaskConical },
  { name: 'Decide', icon: Brain },
  { name: 'Actuate', icon: Zap },
  { name: 'Learn', icon: GraduationCap },
]

const statusIcon: Record<PhaseStatus, typeof CheckCircle2> = {
  pending: Circle,
  running: Loader2,
  complete: CheckCircle2,
  error: AlertCircle,
}

const statusColor: Record<PhaseStatus, string> = {
  pending: 'text-slate-500',
  running: 'text-blue-400',
  complete: 'text-green-400',
  error: 'text-red-400',
}

const statusBg: Record<PhaseStatus, string> = {
  pending: 'bg-slate-700/50',
  running: 'bg-blue-500/20 ring-1 ring-blue-500/30',
  complete: 'bg-green-500/10',
  error: 'bg-red-500/20 ring-1 ring-red-500/30',
}

const connectorColor: Record<PhaseStatus, string> = {
  pending: 'bg-slate-700',
  running: 'bg-blue-500/50',
  complete: 'bg-green-500/50',
  error: 'bg-red-500/50',
}

export default function CycleTimeline({ phases, compact = false }: CycleTimelineProps) {
  const resolvedPhases: Phase[] = phases
    ? phases
    : phaseDefaults.map((p) => ({ name: p.name, status: 'pending' as PhaseStatus }))

  return (
    <div className="flex items-center justify-between w-full gap-1">
      {resolvedPhases.map((phase, idx) => {
        const phaseDef = phaseDefaults[idx] || phaseDefaults[0]
        const PhaseIcon = phaseDef.icon
        const StatusIconComp = statusIcon[phase.status]
        const isLast = idx === resolvedPhases.length - 1

        return (
          <div key={phase.name} className="flex items-center flex-1">
            <div
              className={clsx(
                'flex flex-col items-center gap-1.5 flex-1',
                compact ? 'min-w-0' : ''
              )}
            >
              <div
                className={clsx(
                  'rounded-xl flex items-center justify-center transition-all',
                  statusBg[phase.status],
                  compact ? 'w-10 h-10' : 'w-14 h-14'
                )}
              >
                <PhaseIcon
                  className={clsx(
                    statusColor[phase.status],
                    compact ? 'w-5 h-5' : 'w-6 h-6',
                    phase.status === 'running' && 'animate-spin'
                  )}
                />
              </div>
              <div className="flex items-center gap-1">
                <StatusIconComp
                  className={clsx(
                    'w-3 h-3',
                    statusColor[phase.status],
                    phase.status === 'running' && 'animate-spin'
                  )}
                />
                <span
                  className={clsx(
                    'font-medium',
                    compact ? 'text-[10px]' : 'text-xs',
                    statusColor[phase.status]
                  )}
                >
                  {phase.name}
                </span>
              </div>
              {phase.duration !== undefined && !compact && (
                <span className="text-[10px] text-slate-500">
                  {phase.duration}ms
                </span>
              )}
            </div>
            {!isLast && (
              <div
                className={clsx(
                  'h-0.5 flex-shrink-0 rounded-full transition-all',
                  compact ? 'w-4' : 'w-8',
                  connectorColor[phase.status]
                )}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}
