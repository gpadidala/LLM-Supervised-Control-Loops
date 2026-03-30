import { useEffect, useState } from 'react'
import { useSCLStore } from '@/store/scl.store'
import ConfidenceGauge from '@/components/ConfidenceGauge'
import MetricChart from '@/components/MetricChart'
import clsx from 'clsx'
import { AlertTriangle, Lightbulb, BarChart3 } from 'lucide-react'
import type { HorizonForecast, QuantileForecast } from '@/types'

export default function Predictions() {
  const { predictions, fetchPredictions } = useSCLStore()
  const [activeHorizon, setActiveHorizon] = useState(0)

  useEffect(() => {
    fetchPredictions()
    const interval = setInterval(fetchPredictions, 10000)
    return () => clearInterval(interval)
  }, [fetchPredictions])

  const risk = predictions?.risk_assessment
  const horizons = predictions?.horizons || []
  const causalInsights = predictions?.causal_insights || []
  const confidenceScores = predictions?.confidence_scores || {}

  const currentHorizon: HorizonForecast | undefined = horizons[activeHorizon]

  // Build chart data from metric forecasts
  const forecastCharts: { name: string; forecast: QuantileForecast }[] = currentHorizon
    ? Object.entries(currentHorizon.metric_forecasts).map(([name, forecast]) => ({
        name,
        forecast: forecast as QuantileForecast,
      }))
    : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-white">Predictions</h2>
        <p className="text-sm text-slate-400 mt-1">
          Multi-horizon forecasts and risk assessments
        </p>
      </div>

      {/* Risk Assessment Gauges */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card flex flex-col items-center py-4">
          <ConfidenceGauge
            value={1 - (risk?.sla_breach_probability ?? 0)}
            size={140}
            label="SLA Compliance"
          />
          <div className="mt-2 text-center">
            <span className="text-xs text-slate-500">Breach Probability</span>
            <p
              className={clsx(
                'text-lg font-bold',
                (risk?.sla_breach_probability ?? 0) > 0.3
                  ? 'text-red-400'
                  : (risk?.sla_breach_probability ?? 0) > 0.1
                  ? 'text-yellow-400'
                  : 'text-green-400'
              )}
            >
              {((risk?.sla_breach_probability ?? 0) * 100).toFixed(1)}%
            </p>
          </div>
        </div>

        <div className="card flex flex-col items-center py-4">
          <ConfidenceGauge
            value={1 - (risk?.cascading_failure_probability ?? 0)}
            size={140}
            label="Cascade Safety"
          />
          <div className="mt-2 text-center">
            <span className="text-xs text-slate-500">Cascade Probability</span>
            <p
              className={clsx(
                'text-lg font-bold',
                (risk?.cascading_failure_probability ?? 0) > 0.2
                  ? 'text-red-400'
                  : (risk?.cascading_failure_probability ?? 0) > 0.05
                  ? 'text-yellow-400'
                  : 'text-green-400'
              )}
            >
              {((risk?.cascading_failure_probability ?? 0) * 100).toFixed(1)}%
            </p>
          </div>
        </div>

        <div className="card flex flex-col items-center py-4">
          <ConfidenceGauge
            value={1 - (risk?.cost_overrun_probability ?? 0)}
            size={140}
            label="Cost Control"
          />
          <div className="mt-2 text-center">
            <span className="text-xs text-slate-500">Cost Overrun Prob.</span>
            <p
              className={clsx(
                'text-lg font-bold',
                (risk?.cost_overrun_probability ?? 0) > 0.25
                  ? 'text-red-400'
                  : (risk?.cost_overrun_probability ?? 0) > 0.1
                  ? 'text-yellow-400'
                  : 'text-green-400'
              )}
            >
              {((risk?.cost_overrun_probability ?? 0) * 100).toFixed(1)}%
            </p>
          </div>
        </div>
      </div>

      {/* Horizon Tabs */}
      {horizons.length > 0 && (
        <div className="flex items-center gap-1 bg-slate-800/50 p-1 rounded-xl border border-slate-700/50">
          {horizons.map((h, idx) => (
            <button
              key={idx}
              onClick={() => setActiveHorizon(idx)}
              className={clsx(
                'flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all',
                activeHorizon === idx ? 'tab-active' : 'tab-inactive'
              )}
            >
              {h.horizon_label || `${h.horizon_seconds}s`}
            </button>
          ))}
        </div>
      )}

      {/* Metric Forecasts with Confidence Bands */}
      {forecastCharts.length > 0 ? (
        <div className="grid grid-cols-2 gap-4">
          {forecastCharts.map((fc) => (
            <MetricChart
              key={fc.name}
              title={fc.name}
              data={[
                {
                  timestamp: new Date().toISOString(),
                  value: fc.forecast.q50,
                  q10: fc.forecast.q10,
                  q90: fc.forecast.q90,
                },
              ]}
              showBands={true}
              color="#3b82f6"
              height={180}
            />
          ))}
        </div>
      ) : (
        <div className="card h-48 flex items-center justify-center text-slate-500">
          No forecast data available. Start the governor to generate predictions.
        </div>
      )}

      {/* Bottom row: Causal Insights + Model Contributions */}
      <div className="grid grid-cols-2 gap-4">
        {/* Causal Insights */}
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <Lightbulb className="w-3.5 h-3.5 text-yellow-400" />
            Causal Insights
          </div>
          {causalInsights.length > 0 ? (
            <ul className="space-y-2">
              {causalInsights.map((insight, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                  <span className="w-5 h-5 rounded-full bg-yellow-500/20 text-yellow-400 flex items-center justify-center text-[10px] font-bold flex-shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  {insight}
                </li>
              ))}
            </ul>
          ) : (
            <div className="h-24 flex items-center justify-center text-sm text-slate-500">
              No causal insights available
            </div>
          )}
        </div>

        {/* Model Contribution Breakdown */}
        <div className="card">
          <div className="card-header flex items-center gap-2">
            <BarChart3 className="w-3.5 h-3.5 text-blue-400" />
            Model Confidence Scores
          </div>
          {Object.keys(confidenceScores).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(confidenceScores).map(([model, score]) => (
                <div key={model}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-slate-400">{model}</span>
                    <span className="text-slate-300 font-mono">
                      {((score as number) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={clsx(
                        'h-full rounded-full transition-all',
                        (score as number) >= 0.8
                          ? 'bg-green-500'
                          : (score as number) >= 0.6
                          ? 'bg-blue-500'
                          : (score as number) >= 0.4
                          ? 'bg-yellow-500'
                          : 'bg-red-500'
                      )}
                      style={{ width: `${(score as number) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-24 flex items-center justify-center text-sm text-slate-500">
              No model data available
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
