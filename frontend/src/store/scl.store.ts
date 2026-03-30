import { create } from 'zustand'
import type {
  GovernorStatus,
  SystemState,
  ControlCycleOutput,
  Decision,
  ConfigData,
  PredictionOutput,
  SimulationResult,
  AnomalyScore,
} from '@/types'
import { api, connectWebSocket } from '@/api/client'

interface SCLStore {
  status: GovernorStatus | null
  currentState: SystemState | null
  latestCycle: ControlCycleOutput | null
  cycles: ControlCycleOutput[]
  decisions: Decision[]
  predictions: PredictionOutput | null
  simulations: SimulationResult[]
  anomalies: AnomalyScore[]
  config: ConfigData | null
  ws: WebSocket | null
  loading: boolean
  error: string | null
  fetchStatus: () => Promise<void>
  fetchCycles: () => Promise<void>
  fetchTelemetry: () => Promise<void>
  fetchDecisions: () => Promise<void>
  fetchPredictions: () => Promise<void>
  fetchSimulations: () => Promise<void>
  fetchAnomalies: () => Promise<void>
  fetchConfig: () => Promise<void>
  startGovernor: () => Promise<void>
  stopGovernor: () => Promise<void>
  triggerCycle: () => Promise<void>
  connectWs: () => void
  disconnectWs: () => void
  handleCycleUpdate: (cycle: ControlCycleOutput) => void
  setError: (error: string | null) => void
}

export const useSCLStore = create<SCLStore>((set, get) => ({
  status: null,
  currentState: null,
  latestCycle: null,
  cycles: [],
  decisions: [],
  predictions: null,
  simulations: [],
  anomalies: [],
  config: null,
  ws: null,
  loading: false,
  error: null,

  setError: (error) => set({ error }),

  fetchStatus: async () => {
    try {
      const status = await api.governor.getStatus()
      set({ status })
    } catch (err: any) {
      console.warn('Failed to fetch status:', err.message)
    }
  },

  fetchCycles: async () => {
    try {
      const cycles = await api.governor.getCycles(50)
      set({ cycles, latestCycle: cycles.length > 0 ? cycles[0] : null })
    } catch (err: any) {
      console.warn('Failed to fetch cycles:', err.message)
    }
  },

  fetchTelemetry: async () => {
    try {
      const currentState = await api.telemetry.getCurrent()
      set({ currentState })
    } catch (err: any) {
      console.warn('Failed to fetch telemetry:', err.message)
    }
  },

  fetchDecisions: async () => {
    try {
      const decisions = await api.decisions.list()
      set({ decisions })
    } catch (err: any) {
      console.warn('Failed to fetch decisions:', err.message)
    }
  },

  fetchPredictions: async () => {
    try {
      const predictions = await api.predictions.getLatest()
      set({ predictions })
    } catch (err: any) {
      console.warn('Failed to fetch predictions:', err.message)
    }
  },

  fetchSimulations: async () => {
    try {
      const simulations = await api.simulation.getLatest()
      set({ simulations: Array.isArray(simulations) ? simulations : [] })
    } catch (err: any) {
      console.warn('Failed to fetch simulations:', err.message)
    }
  },

  fetchAnomalies: async () => {
    try {
      const anomalies = await api.telemetry.getAnomalies()
      set({ anomalies: Array.isArray(anomalies) ? anomalies : [] })
    } catch (err: any) {
      console.warn('Failed to fetch anomalies:', err.message)
    }
  },

  fetchConfig: async () => {
    try {
      const config = await api.config.get()
      set({ config })
    } catch (err: any) {
      console.warn('Failed to fetch config:', err.message)
    }
  },

  startGovernor: async () => {
    try {
      set({ loading: true })
      await api.governor.start()
      await get().fetchStatus()
      set({ loading: false })
    } catch (err: any) {
      set({ loading: false, error: err.message })
    }
  },

  stopGovernor: async () => {
    try {
      set({ loading: true })
      await api.governor.stop()
      await get().fetchStatus()
      set({ loading: false })
    } catch (err: any) {
      set({ loading: false, error: err.message })
    }
  },

  triggerCycle: async () => {
    try {
      set({ loading: true })
      const cycle = await api.governor.triggerCycle()
      get().handleCycleUpdate(cycle)
      set({ loading: false })
    } catch (err: any) {
      set({ loading: false, error: err.message })
    }
  },

  connectWs: () => {
    const existing = get().ws
    if (existing && existing.readyState === WebSocket.OPEN) return
    const ws = connectWebSocket((cycle) => {
      get().handleCycleUpdate(cycle)
    })
    set({ ws })
  },

  disconnectWs: () => {
    const ws = get().ws
    if (ws) {
      ws.close()
      set({ ws: null })
    }
  },

  handleCycleUpdate: (cycle) => {
    set((state) => ({
      latestCycle: cycle,
      cycles: [cycle, ...state.cycles].slice(0, 100),
      status: state.status
        ? {
            ...state.status,
            current_regime: cycle.system_regime,
            cycle_count: (state.status.cycle_count || 0) + 1,
          }
        : state.status,
    }))
  },
}))
