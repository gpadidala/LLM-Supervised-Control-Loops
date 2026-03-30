import { useEffect, useState } from 'react'
import { useSCLStore } from '@/store/scl.store'
import { api } from '@/api/client'
import {
  Save,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Sliders,
  Shield,
  Link,
} from 'lucide-react'
import clsx from 'clsx'
import type { ConfigData } from '@/types'

export default function Settings() {
  const { config, fetchConfig } = useSCLStore()
  const [localConfig, setLocalConfig] = useState<ConfigData | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    fetchConfig()
  }, [fetchConfig])

  useEffect(() => {
    if (config) {
      setLocalConfig(JSON.parse(JSON.stringify(config)))
    }
  }, [config])

  const handleSave = async () => {
    if (!localConfig) return
    setSaving(true)
    try {
      await api.config.update(localConfig)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      fetchConfig()
    } catch (err) {
      console.error('Failed to save config:', err)
    }
    setSaving(false)
  }

  const updateWeight = (key: string, value: number) => {
    if (!localConfig) return
    setLocalConfig({
      ...localConfig,
      objective_weights: {
        ...localConfig.objective_weights,
        [key]: value,
      },
    })
  }

  const updateThreshold = (key: string, value: number) => {
    if (!localConfig) return
    setLocalConfig({
      ...localConfig,
      confidence_thresholds: {
        ...localConfig.confidence_thresholds,
        [key]: value,
      },
    })
  }

  // Defaults for when config hasn't loaded
  const defaultConfig: ConfigData = {
    cycle_interval_seconds: 10,
    objective_weights: {
      performance: 0.3,
      cost: 0.2,
      risk: 0.2,
      stability: 0.15,
      business: 0.15,
    },
    confidence_thresholds: {
      high: 0.85,
      medium: 0.65,
      low: 0.4,
    },
    safety_constraints: {
      min_replicas: 2,
      budget_ceiling: 10000,
      max_blast_radius: 0.3,
      max_concurrent_changes: 3,
      cooldown_seconds: 60,
    },
    connectors: {
      prometheus: false,
      kubernetes: false,
      llm: false,
      slack: false,
      pagerduty: false,
    },
  }

  const cfg = localConfig || defaultConfig

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white">Settings</h2>
          <p className="text-sm text-slate-400 mt-1">
            Configure the SCL-Governor control parameters
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saved && (
            <span className="flex items-center gap-1 text-sm text-green-400">
              <CheckCircle2 className="w-4 h-4" />
              Saved
            </span>
          )}
          <button
            onClick={handleSave}
            disabled={saving || !localConfig}
            className="btn-primary flex items-center gap-2"
          >
            {saving ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Save Configuration
          </button>
        </div>
      </div>

      {/* Control Cycle Interval */}
      <div className="card">
        <div className="card-header">Control Cycle Interval</div>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={1}
            max={60}
            value={cfg.cycle_interval_seconds}
            onChange={(e) =>
              setLocalConfig({
                ...cfg,
                cycle_interval_seconds: parseInt(e.target.value),
              })
            }
            className="flex-1 h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
          <div className="w-20 text-center">
            <span className="text-2xl font-bold text-white">
              {cfg.cycle_interval_seconds}
            </span>
            <span className="text-sm text-slate-400 ml-1">s</span>
          </div>
        </div>
        <div className="flex items-center justify-between mt-2 text-xs text-slate-500">
          <span>1s (aggressive)</span>
          <span>60s (conservative)</span>
        </div>
      </div>

      {/* Objective Weights */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Sliders className="w-3.5 h-3.5 text-blue-400" />
          Objective Weights
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Balance the multi-objective optimization function. Weights should ideally sum to 1.0.
        </p>
        <div className="space-y-4">
          {Object.entries(cfg.objective_weights).map(([key, value]) => {
            const colorMap: Record<string, string> = {
              performance: 'accent-green-500',
              cost: 'accent-red-500',
              risk: 'accent-yellow-500',
              stability: 'accent-blue-500',
              business: 'accent-purple-500',
            }
            const labelColor: Record<string, string> = {
              performance: 'text-green-400',
              cost: 'text-red-400',
              risk: 'text-yellow-400',
              stability: 'text-blue-400',
              business: 'text-purple-400',
            }
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className={clsx('capitalize font-medium', labelColor[key] || 'text-slate-300')}>
                    {key}
                  </span>
                  <span className="text-slate-400 font-mono text-xs">
                    {(value as number).toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round((value as number) * 100)}
                  onChange={(e) =>
                    updateWeight(key, parseInt(e.target.value) / 100)
                  }
                  className={clsx(
                    'w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer',
                    colorMap[key] || 'accent-blue-500'
                  )}
                />
              </div>
            )
          })}
          <div className="pt-2 border-t border-slate-700/50">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">Total Weight</span>
              <span
                className={clsx(
                  'font-mono font-medium',
                  Math.abs(
                    Object.values(cfg.objective_weights).reduce(
                      (a, b) => a + (b as number),
                      0
                    ) - 1
                  ) < 0.05
                    ? 'text-green-400'
                    : 'text-amber-400'
                )}
              >
                {Object.values(cfg.objective_weights)
                  .reduce((a, b) => a + (b as number), 0)
                  .toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Confidence Thresholds */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-green-400" />
          Confidence Thresholds
        </div>
        <p className="text-xs text-slate-500 mb-4">
          Thresholds determine autonomy level. Above &quot;high&quot; = autonomous, above &quot;medium&quot; = notify, above &quot;low&quot; = recommend, below = escalate.
        </p>
        <div className="space-y-4">
          {Object.entries(cfg.confidence_thresholds).map(([key, value]) => {
            const colorMap: Record<string, string> = {
              high: 'text-green-400',
              medium: 'text-yellow-400',
              low: 'text-red-400',
            }
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className={clsx('capitalize font-medium', colorMap[key])}>
                    {key}
                  </span>
                  <span className="text-slate-400 font-mono text-xs">
                    {((value as number) * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={Math.round((value as number) * 100)}
                  onChange={(e) =>
                    updateThreshold(key, parseInt(e.target.value) / 100)
                  }
                  className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                />
              </div>
            )
          })}
        </div>
      </div>

      {/* Safety Constraints */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-red-400" />
          Safety Constraints
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-slate-900/50 rounded-lg p-3">
            <span className="text-xs text-slate-500">Min Replicas</span>
            <p className="text-lg font-bold text-slate-200 mt-1">
              {cfg.safety_constraints.min_replicas}
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3">
            <span className="text-xs text-slate-500">Budget Ceiling</span>
            <p className="text-lg font-bold text-slate-200 mt-1">
              ${cfg.safety_constraints.budget_ceiling.toLocaleString()}/mo
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3">
            <span className="text-xs text-slate-500">Max Blast Radius</span>
            <p className="text-lg font-bold text-slate-200 mt-1">
              {(cfg.safety_constraints.max_blast_radius * 100).toFixed(0)}%
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3">
            <span className="text-xs text-slate-500">Max Concurrent Changes</span>
            <p className="text-lg font-bold text-slate-200 mt-1">
              {cfg.safety_constraints.max_concurrent_changes}
            </p>
          </div>
          <div className="bg-slate-900/50 rounded-lg p-3 col-span-2">
            <span className="text-xs text-slate-500">Cooldown Period</span>
            <p className="text-lg font-bold text-slate-200 mt-1">
              {cfg.safety_constraints.cooldown_seconds}s
            </p>
          </div>
        </div>
      </div>

      {/* Connector Status */}
      <div className="card">
        <div className="card-header flex items-center gap-2">
          <Link className="w-3.5 h-3.5 text-purple-400" />
          Connector Status
        </div>
        <div className="grid grid-cols-5 gap-3">
          {Object.entries(cfg.connectors).map(([name, connected]) => (
            <div
              key={name}
              className={clsx(
                'rounded-lg p-3 text-center border transition-all',
                connected
                  ? 'bg-green-500/10 border-green-500/30'
                  : 'bg-slate-800/50 border-slate-700/30'
              )}
            >
              {connected ? (
                <CheckCircle2 className="w-5 h-5 text-green-400 mx-auto mb-1" />
              ) : (
                <XCircle className="w-5 h-5 text-slate-500 mx-auto mb-1" />
              )}
              <span
                className={clsx(
                  'text-xs font-medium capitalize',
                  connected ? 'text-green-400' : 'text-slate-500'
                )}
              >
                {name}
              </span>
              <p className="text-[10px] text-slate-600 mt-0.5">
                {connected ? 'Connected' : 'Disconnected'}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
