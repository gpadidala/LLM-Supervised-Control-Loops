import clsx from 'clsx'
import type { Regime } from '@/types'

interface RegimeBadgeProps {
  regime: Regime
  size?: 'sm' | 'md' | 'lg'
}

const regimeConfig: Record<Regime, { label: string; bg: string; text: string; ring: string; pulse?: boolean }> = {
  normal: {
    label: 'Normal',
    bg: 'bg-green-500/20',
    text: 'text-green-400',
    ring: 'ring-green-500/30',
  },
  degraded: {
    label: 'Degraded',
    bg: 'bg-yellow-500/20',
    text: 'text-yellow-400',
    ring: 'ring-yellow-500/30',
  },
  critical: {
    label: 'Critical',
    bg: 'bg-red-500/20',
    text: 'text-red-400',
    ring: 'ring-red-500/30',
    pulse: true,
  },
  recovery: {
    label: 'Recovery',
    bg: 'bg-blue-500/20',
    text: 'text-blue-400',
    ring: 'ring-blue-500/30',
  },
  maintenance: {
    label: 'Maintenance',
    bg: 'bg-purple-500/20',
    text: 'text-purple-400',
    ring: 'ring-purple-500/30',
  },
}

const sizeClasses = {
  sm: 'px-2 py-0.5 text-[10px]',
  md: 'px-3 py-1 text-xs',
  lg: 'px-4 py-1.5 text-sm',
}

export default function RegimeBadge({ regime, size = 'md' }: RegimeBadgeProps) {
  const config = regimeConfig[regime] || regimeConfig.normal

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full font-semibold ring-1',
        config.bg,
        config.text,
        config.ring,
        sizeClasses[size],
        config.pulse && 'animate-pulse'
      )}
    >
      <span
        className={clsx(
          'w-1.5 h-1.5 rounded-full',
          regime === 'normal' && 'bg-green-400',
          regime === 'degraded' && 'bg-yellow-400',
          regime === 'critical' && 'bg-red-400',
          regime === 'recovery' && 'bg-blue-400',
          regime === 'maintenance' && 'bg-purple-400'
        )}
      />
      {config.label}
    </span>
  )
}
