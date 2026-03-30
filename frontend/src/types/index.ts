export type Regime = 'normal' | 'degraded' | 'critical' | 'recovery' | 'maintenance'
export type AutonomyLevel = 'execute_autonomous' | 'execute_with_notification' | 'recommend' | 'escalate'

export interface MetricValue {
  name: string
  value: number
  timestamp: string
  labels: Record<string, string>
  unit: string
}

export interface TelemetryVector {
  signal_class: string
  metrics: MetricValue[]
  source: string
}

export interface TrendVector {
  metric_name: string
  delta_5min: number
  delta_15min: number
  delta_1hr: number
}

export interface AnomalyScore {
  metric_name: string
  z_score: number
  mad_score: number
  is_anomalous: boolean
  causal_attribution: string[]
}

export interface DerivedMetrics {
  trend_vectors: TrendVector[]
  anomaly_scores: AnomalyScore[]
  correlation_matrix: Record<string, Record<string, number>>
  seasonality_phase: Record<string, number>
}

export interface SystemState {
  timestamp: string
  cycle_id: string
  infrastructure: TelemetryVector
  application: TelemetryVector
  business: TelemetryVector
  network: TelemetryVector
  cost: TelemetryVector
  derived: DerivedMetrics
  regime: Regime
}

export interface QuantileForecast {
  q10: number
  q50: number
  q90: number
}

export interface RiskAssessment {
  sla_breach_probability: number
  cascading_failure_probability: number
  cost_overrun_probability: number
}

export interface HorizonForecast {
  horizon_seconds: number
  horizon_label: string
  metric_forecasts: Record<string, QuantileForecast>
}

export interface PredictionOutput {
  timestamp: string
  cycle_id: string
  horizons: HorizonForecast[]
  risk_assessment: RiskAssessment
  causal_insights: string[]
  confidence_scores: Record<string, number>
}

export interface ActionCandidate {
  id: string
  type: string
  description: string
  parameters: Record<string, any>
  target_service: string | null
  blast_radius: number
  reversibility: number
  estimated_cost_delta: number
}

export interface SimulationResult {
  action_id: string
  action_description: string
  n_scenarios: number
  expected_objective: number
  var_alpha: number
  cvar_alpha: number
  sla_breach_probability: number
  expected_cost_delta: number
  is_pareto_optimal: boolean
}

export interface Decision {
  cycle_id: string
  timestamp: string
  selected_action: ActionCandidate
  reasoning: string
  confidence: number
  autonomy_level: AutonomyLevel
  alternative_actions: any[]
  rollback_plan: string
  rollback_trigger: string
}

export interface ControlCycleOutput {
  cycle_id: string
  timestamp: string
  system_regime: Regime
  state_summary: {
    top_concerns: string[]
    anomalies_detected: number
    sla_breach_eta_minutes: number | null
  }
  prediction: any
  simulation_results: any
  decision: any
  execution_status: string
  learning_update: any
}

export interface GovernorStatus {
  is_running: boolean
  cycle_count: number
  current_regime: Regime
  uptime_seconds: number
}

export interface LearningMetrics {
  prediction_accuracy: number[]
  simulation_fidelity: number[]
  reward_history: number[]
  model_drift: number
  human_override_count: number
  replay_buffer_size: number
}

export interface ConfigData {
  cycle_interval_seconds: number
  objective_weights: {
    performance: number
    cost: number
    risk: number
    stability: number
    business: number
  }
  confidence_thresholds: {
    high: number
    medium: number
    low: number
  }
  safety_constraints: {
    min_replicas: number
    budget_ceiling: number
    max_blast_radius: number
    max_concurrent_changes: number
    cooldown_seconds: number
  }
  connectors: {
    prometheus: boolean
    kubernetes: boolean
    llm: boolean
    slack: boolean
    pagerduty: boolean
  }
}

export type ConnectionStatus = 'connected' | 'disconnected' | 'error' | 'testing' | 'pending'
export type Environment = 'production' | 'staging' | 'development'

export interface ServiceEndpoint {
  name: string
  namespace: string
  port: number
  protocol: string
  health_check_path: string
  metrics_path: string
  slo_latency_p99_ms: number
  slo_error_rate_percent: number
  slo_availability_percent: number
  labels: Record<string, string>
}

export interface ApplicationConnection {
  id: string
  name: string
  description: string
  environment: Environment
  created_at: string
  updated_at: string
  status: ConnectionStatus
  prometheus: {
    url: string
    username: string
    password: string
    bearer_token: string
    tls_skip_verify: boolean
  }
  kubernetes: {
    enabled: boolean
    cluster_name: string
    kubeconfig_path: string
    in_cluster: boolean
    namespace: string
  }
  services: ServiceEndpoint[]
  notifications: {
    slack_webhook_url: string
    slack_channel: string
    pagerduty_api_key: string
    pagerduty_service_id: string
  }
  llm: {
    provider: string
    model: string
    api_key: string
    temperature: number
    max_tokens: number
  }
  cycle_interval_seconds: number
  simulation_scenarios: number
  auto_start: boolean
  last_telemetry_at: string | null
  last_error: string | null
  telemetry_metrics_count: number
}

export interface ConnectionTestResult {
  connection_id: string
  timestamp: string
  prometheus_ok: boolean
  prometheus_message: string
  prometheus_metrics_count: number
  kubernetes_ok: boolean
  kubernetes_message: string
  kubernetes_nodes: number
  services_reachable: Record<string, boolean>
  llm_ok: boolean
  llm_message: string
  overall_ok: boolean
}
