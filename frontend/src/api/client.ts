import type {
  GovernorStatus,
  ControlCycleOutput,
  SystemState,
  AnomalyScore,
  Decision,
  ConfigData,
  SimulationResult,
  PredictionOutput,
} from '@/types'

const API_BASE = '/api/v1'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function post<T = any>(path: string, body?: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

async function put<T = any>(path: string, body: any): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`PUT ${path} failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  governor: {
    getStatus: () => get<GovernorStatus>('/governor/status'),
    start: () => post('/governor/start'),
    stop: () => post('/governor/stop'),
    triggerCycle: () => post<ControlCycleOutput>('/governor/cycle'),
    getCycles: (limit = 20) =>
      get<ControlCycleOutput[]>(`/governor/cycles?limit=${limit}`),
  },
  telemetry: {
    getCurrent: () => get<SystemState>('/telemetry/current'),
    getHistory: (limit = 100) =>
      get<SystemState[]>(`/telemetry/history?limit=${limit}`),
    getAnomalies: () => get<AnomalyScore[]>('/telemetry/anomalies'),
  },
  predictions: {
    getLatest: async (): Promise<PredictionOutput | null> => {
      // Prediction data is embedded in cycle outputs
      const cycles = await get<ControlCycleOutput[]>('/governor/cycles?limit=1')
      return cycles.length > 0 ? cycles[0].prediction : null
    },
  },
  decisions: {
    list: () => get<Decision[]>('/decisions/'),
    getStats: () => get<any>('/decisions/stats'),
    override: (data: any) => post('/decisions/override', data),
  },
  simulation: {
    getLatest: () => get<SimulationResult[]>('/simulation/latest'),
    getPareto: () => get<SimulationResult[]>('/simulation/pareto'),
  },
  learning: {
    getMetrics: async (): Promise<any> => {
      // Learning data is embedded in cycle outputs
      const cycles = await get<ControlCycleOutput[]>('/governor/cycles?limit=50')
      return {
        cycles: cycles.map((c) => ({
          cycle_id: c.cycle_id,
          timestamp: c.timestamp,
          ...c.learning_update,
        })),
      }
    },
  },
  connections: {
    list: () => get<any[]>('/connections/'),
    get: (id: string) => get<any>(`/connections/${id}`),
    create: (data: any) => post<any>('/connections/', data),
    update: (id: string, data: any) => put<any>(`/connections/${id}`, data),
    delete: (id: string) => fetch(`${API_BASE}/connections/${id}`, { method: 'DELETE' }).then(r => r.json()),
    test: (id: string) => post<any>(`/connections/${id}/test`),
    activate: (id: string) => post<any>(`/connections/${id}/activate`),
  },
  config: {
    get: () => get<ConfigData>('/config/'),
    updateWeights: (w: any) => put('/config/weights', w),
    updateThresholds: (t: any) => put('/config/thresholds', t),
    update: (c: Partial<ConfigData>) => put('/config/', c),
  },
}

export function connectWebSocket(
  onMessage: (data: ControlCycleOutput) => void
): WebSocket {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${location.host}/api/v1/ws/cycles`)

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onMessage(data)
    } catch {
      console.warn('Failed to parse WebSocket message')
    }
  }

  ws.onerror = (err) => {
    console.warn('WebSocket error:', err)
  }

  ws.onclose = () => {
    console.info('WebSocket closed, reconnecting in 3s...')
    setTimeout(() => connectWebSocket(onMessage), 3000)
  }

  return ws
}
