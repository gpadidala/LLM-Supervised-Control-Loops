import { useEffect, useState, useCallback } from 'react'
import { api } from '@/api/client'
import type { ApplicationConnection, ConnectionTestResult, ServiceEndpoint, Environment, ConnectionStatus } from '@/types'
import clsx from 'clsx'
import {
  Plug,
  Plus,
  Trash2,
  TestTube,
  Check,
  X,
  ArrowRight,
  ArrowLeft,
  Server,
  Database,
  Bell,
  Brain,
  Shield,
  Globe,
  RefreshCw,
  Pencil,
  Zap,
  AlertCircle,
} from 'lucide-react'

const STEPS = [
  { label: 'Basic Info', icon: Globe },
  { label: 'Prometheus', icon: Database },
  { label: 'Services & SLOs', icon: Server },
  { label: 'Kubernetes', icon: Shield },
  { label: 'Notifications', icon: Bell },
  { label: 'LLM Config', icon: Brain },
  { label: 'Review', icon: Check },
]

const ENV_COLORS: Record<Environment, string> = {
  production: 'bg-red-500/20 text-red-400 border-red-500/30',
  staging: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  development: 'bg-green-500/20 text-green-400 border-green-500/30',
}

const STATUS_STYLES: Record<ConnectionStatus, { dot: string; label: string }> = {
  connected: { dot: 'bg-green-400', label: 'Connected' },
  disconnected: { dot: 'bg-slate-500', label: 'Disconnected' },
  error: { dot: 'bg-red-500', label: 'Error' },
  testing: { dot: 'bg-yellow-400 animate-pulse', label: 'Testing...' },
  pending: { dot: 'bg-blue-400', label: 'Pending' },
}

function emptyService(): ServiceEndpoint {
  return {
    name: '',
    namespace: 'default',
    port: 8080,
    protocol: 'http',
    health_check_path: '/healthz',
    metrics_path: '/metrics',
    slo_latency_p99_ms: 500,
    slo_error_rate_percent: 1,
    slo_availability_percent: 99.9,
    labels: {},
  }
}

function emptyForm() {
  return {
    name: '',
    description: '',
    environment: 'development' as Environment,
    prometheus: { url: '', username: '', password: '', bearer_token: '', tls_skip_verify: false },
    kubernetes: { enabled: false, cluster_name: '', kubeconfig_path: '', in_cluster: false, namespace: 'default' },
    services: [emptyService()] as ServiceEndpoint[],
    notifications: { slack_webhook_url: '', slack_channel: '', pagerduty_api_key: '', pagerduty_service_id: '' },
    llm: { provider: 'anthropic', model: 'claude-sonnet-4-20250514', api_key: '', temperature: 0.1, max_tokens: 4096 },
    cycle_interval_seconds: 10,
    simulation_scenarios: 50,
    auto_start: true,
  }
}

export default function Connections() {
  const [connections, setConnections] = useState<ApplicationConnection[]>([])
  const [loading, setLoading] = useState(true)
  const [wizardOpen, setWizardOpen] = useState(false)
  const [step, setStep] = useState(0)
  const [form, setForm] = useState(emptyForm())
  const [saving, setSaving] = useState(false)
  const [testResults, setTestResults] = useState<ConnectionTestResult | null>(null)
  const [testingAll, setTestingAll] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [testingIds, setTestingIds] = useState<Set<string>>(new Set())

  const showToast = useCallback((message: string, type: 'success' | 'error') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchConnections = useCallback(async () => {
    try {
      const data = await api.connections.list()
      setConnections(data)
    } catch {
      // Use demo data when API is unavailable
      setConnections([
        {
          id: 'demo-connection',
          name: 'Demo Environment',
          description: 'Built-in simulated environment for exploring the SCL-Governor',
          environment: 'development',
          created_at: '2025-01-01T00:00:00Z',
          updated_at: new Date().toISOString(),
          status: 'connected',
          prometheus: { url: 'http://localhost:9090', username: '', password: '', bearer_token: '', tls_skip_verify: false },
          kubernetes: { enabled: false, cluster_name: '', kubeconfig_path: '', in_cluster: false, namespace: '' },
          services: [
            { name: 'api-gateway', namespace: 'default', port: 8080, protocol: 'http', health_check_path: '/healthz', metrics_path: '/metrics', slo_latency_p99_ms: 200, slo_error_rate_percent: 0.5, slo_availability_percent: 99.95, labels: {} },
            { name: 'payment-service', namespace: 'default', port: 8081, protocol: 'http', health_check_path: '/healthz', metrics_path: '/metrics', slo_latency_p99_ms: 300, slo_error_rate_percent: 0.1, slo_availability_percent: 99.99, labels: {} },
          ],
          notifications: { slack_webhook_url: '', slack_channel: '', pagerduty_api_key: '', pagerduty_service_id: '' },
          llm: { provider: 'anthropic', model: 'claude-sonnet-4-20250514', api_key: '***', temperature: 0.1, max_tokens: 4096 },
          cycle_interval_seconds: 10,
          simulation_scenarios: 50,
          auto_start: true,
          last_telemetry_at: new Date().toISOString(),
          last_error: null,
          telemetry_metrics_count: 847,
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConnections()
  }, [fetchConnections])

  const handleDelete = async (id: string) => {
    if (id === 'demo-connection') return
    if (!confirm('Delete this connection? This cannot be undone.')) return
    try {
      await api.connections.delete(id)
      showToast('Connection deleted', 'success')
      fetchConnections()
    } catch {
      showToast('Failed to delete connection', 'error')
    }
  }

  const handleTest = async (id: string) => {
    setTestingIds((prev) => new Set(prev).add(id))
    try {
      await api.connections.test(id)
      showToast('Connection test successful', 'success')
      fetchConnections()
    } catch {
      showToast('Connection test failed', 'error')
    } finally {
      setTestingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  const handleActivate = async (id: string) => {
    try {
      await api.connections.activate(id)
      showToast('Connection activated', 'success')
      fetchConnections()
    } catch {
      showToast('Failed to activate connection', 'error')
    }
  }

  const handleEdit = (conn: ApplicationConnection) => {
    setEditingId(conn.id)
    setForm({
      name: conn.name,
      description: conn.description,
      environment: conn.environment,
      prometheus: { ...conn.prometheus },
      kubernetes: { ...conn.kubernetes },
      services: conn.services.length > 0 ? conn.services.map((s) => ({ ...s })) : [emptyService()],
      notifications: { ...conn.notifications },
      llm: { ...conn.llm },
      cycle_interval_seconds: conn.cycle_interval_seconds,
      simulation_scenarios: conn.simulation_scenarios,
      auto_start: conn.auto_start,
    })
    setStep(0)
    setTestResults(null)
    setWizardOpen(true)
  }

  const openNewWizard = () => {
    setEditingId(null)
    setForm(emptyForm())
    setStep(0)
    setTestResults(null)
    setWizardOpen(true)
  }

  const handleTestAll = async () => {
    setTestingAll(true)
    try {
      // First save/create, then test
      let connId = editingId
      if (!connId) {
        const created = await api.connections.create(form)
        connId = created.id
        setEditingId(connId)
      } else {
        await api.connections.update(connId, form)
      }
      const results = await api.connections.test(connId)
      setTestResults(results)
      showToast('Connection tests complete', results.overall_ok ? 'success' : 'error')
    } catch {
      setTestResults({
        connection_id: editingId || '',
        timestamp: new Date().toISOString(),
        prometheus_ok: false,
        prometheus_message: 'Failed to reach Prometheus',
        prometheus_metrics_count: 0,
        kubernetes_ok: false,
        kubernetes_message: form.kubernetes.enabled ? 'Failed to reach cluster' : 'Skipped (disabled)',
        kubernetes_nodes: 0,
        services_reachable: {},
        llm_ok: false,
        llm_message: 'Failed to validate LLM credentials',
        overall_ok: false,
      })
      showToast('Connection tests failed', 'error')
    } finally {
      setTestingAll(false)
    }
  }

  const handleSaveActivate = async () => {
    setSaving(true)
    try {
      let connId = editingId
      if (!connId) {
        const created = await api.connections.create(form)
        connId = created.id
      } else {
        await api.connections.update(connId, form)
      }
      await api.connections.activate(connId)
      showToast('Connection saved and activated', 'success')
      setWizardOpen(false)
      fetchConnections()
    } catch {
      showToast('Failed to save connection', 'error')
    } finally {
      setSaving(false)
    }
  }

  const updateForm = <K extends keyof ReturnType<typeof emptyForm>>(key: K, value: ReturnType<typeof emptyForm>[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const updateService = (index: number, field: keyof ServiceEndpoint, value: any) => {
    setForm((prev) => {
      const services = [...prev.services]
      services[index] = { ...services[index], [field]: value }
      return { ...prev, services }
    })
  }

  const addService = () => {
    setForm((prev) => ({ ...prev, services: [...prev.services, emptyService()] }))
  }

  const removeService = (index: number) => {
    setForm((prev) => ({
      ...prev,
      services: prev.services.length > 1 ? prev.services.filter((_, i) => i !== index) : prev.services,
    }))
  }

  // ─── Render helpers ─────────────────────────────────────────────

  const renderStepBasicInfo = () => (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Application Name</label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => updateForm('name', e.target.value)}
          placeholder="my-production-app"
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Description</label>
        <textarea
          value={form.description}
          onChange={(e) => updateForm('description', e.target.value)}
          placeholder="Brief description of this application and what it does..."
          rows={3}
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition resize-none"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Environment</label>
        <select
          value={form.environment}
          onChange={(e) => updateForm('environment', e.target.value as Environment)}
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none transition"
        >
          <option value="production">Production</option>
          <option value="staging">Staging</option>
          <option value="development">Development</option>
        </select>
      </div>
    </div>
  )

  const renderStepPrometheus = () => (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Prometheus URL</label>
        <input
          type="text"
          value={form.prometheus.url}
          onChange={(e) => updateForm('prometheus', { ...form.prometheus, url: e.target.value })}
          placeholder="http://prometheus:9090"
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Username <span className="text-slate-500">(optional)</span></label>
          <input
            type="text"
            value={form.prometheus.username}
            onChange={(e) => updateForm('prometheus', { ...form.prometheus, username: e.target.value })}
            className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1">Password <span className="text-slate-500">(optional)</span></label>
          <input
            type="password"
            value={form.prometheus.password}
            onChange={(e) => updateForm('prometheus', { ...form.prometheus, password: e.target.value })}
            className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition"
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Bearer Token <span className="text-slate-500">(alternative to user/pass)</span></label>
        <input
          type="password"
          value={form.prometheus.bearer_token}
          onChange={(e) => updateForm('prometheus', { ...form.prometheus, bearer_token: e.target.value })}
          placeholder="eyJhbGciOiJIUzI1NiIs..."
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition"
        />
      </div>
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={form.prometheus.tls_skip_verify}
          onChange={(e) => updateForm('prometheus', { ...form.prometheus, tls_skip_verify: e.target.checked })}
          className="accent-blue-500"
        />
        <span className="text-sm text-slate-400">Skip TLS verification</span>
      </label>
    </div>
  )

  const renderStepServices = () => (
    <div className="space-y-4">
      {form.services.map((svc, idx) => (
        <div key={idx} className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-300">Service {idx + 1}</span>
            {form.services.length > 1 && (
              <button onClick={() => removeService(idx)} className="text-red-400 hover:text-red-300 transition">
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-500 mb-1">Service Name</label>
              <input type="text" value={svc.name} onChange={(e) => updateService(idx, 'name', e.target.value)} placeholder="api-gateway" className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Namespace</label>
              <input type="text" value={svc.namespace} onChange={(e) => updateService(idx, 'namespace', e.target.value)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Port</label>
              <input type="number" value={svc.port} onChange={(e) => updateService(idx, 'port', parseInt(e.target.value) || 0)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Health Check Path</label>
              <input type="text" value={svc.health_check_path} onChange={(e) => updateService(idx, 'health_check_path', e.target.value)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Metrics Path</label>
              <input type="text" value={svc.metrics_path} onChange={(e) => updateService(idx, 'metrics_path', e.target.value)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 pt-2 border-t border-slate-700/50">
            <div>
              <label className="block text-xs text-slate-500 mb-1">SLO: Latency P99 (ms)</label>
              <input type="number" value={svc.slo_latency_p99_ms} onChange={(e) => updateService(idx, 'slo_latency_p99_ms', parseInt(e.target.value) || 0)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">SLO: Error Rate (%)</label>
              <input type="number" step="0.1" value={svc.slo_error_rate_percent} onChange={(e) => updateService(idx, 'slo_error_rate_percent', parseFloat(e.target.value) || 0)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">SLO: Availability (%)</label>
              <input type="number" step="0.01" value={svc.slo_availability_percent} onChange={(e) => updateService(idx, 'slo_availability_percent', parseFloat(e.target.value) || 0)} className="w-full bg-slate-900 border border-slate-600 rounded px-2 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none transition" />
            </div>
          </div>
        </div>
      ))}
      <button onClick={addService} className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300 transition">
        <Plus className="w-4 h-4" /> Add Service
      </button>
    </div>
  )

  const renderStepKubernetes = () => (
    <div className="space-y-4">
      <label className="flex items-center gap-3 cursor-pointer">
        <div className={clsx('w-10 h-5 rounded-full transition-colors relative', form.kubernetes.enabled ? 'bg-blue-600' : 'bg-slate-600')} onClick={() => updateForm('kubernetes', { ...form.kubernetes, enabled: !form.kubernetes.enabled })}>
          <div className={clsx('w-4 h-4 bg-white rounded-full absolute top-0.5 transition-all', form.kubernetes.enabled ? 'left-5' : 'left-0.5')} />
        </div>
        <span className="text-sm text-slate-300">Enable Kubernetes Integration</span>
      </label>
      {form.kubernetes.enabled && (
        <div className="space-y-4 pl-1">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Cluster Name</label>
            <input type="text" value={form.kubernetes.cluster_name} onChange={(e) => updateForm('kubernetes', { ...form.kubernetes, cluster_name: e.target.value })} placeholder="my-cluster" className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1">Namespace</label>
            <input type="text" value={form.kubernetes.namespace} onChange={(e) => updateForm('kubernetes', { ...form.kubernetes, namespace: e.target.value })} placeholder="default" className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition" />
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={form.kubernetes.in_cluster} onChange={(e) => updateForm('kubernetes', { ...form.kubernetes, in_cluster: e.target.checked })} className="accent-blue-500" />
            <span className="text-sm text-slate-400">Running in-cluster (use service account)</span>
          </label>
          {!form.kubernetes.in_cluster && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">Kubeconfig Path</label>
              <input type="text" value={form.kubernetes.kubeconfig_path} onChange={(e) => updateForm('kubernetes', { ...form.kubernetes, kubeconfig_path: e.target.value })} placeholder="~/.kube/config" className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition" />
            </div>
          )}
        </div>
      )}
    </div>
  )

  const renderStepNotifications = () => (
    <div className="space-y-6">
      <div>
        <h4 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-5 h-5 rounded bg-purple-500/20 flex items-center justify-center text-[10px] text-purple-400">#</span>
          Slack
        </h4>
        <div className="space-y-3 pl-1">
          <div>
            <label className="block text-xs text-slate-500 mb-1">Webhook URL</label>
            <input type="text" value={form.notifications.slack_webhook_url} onChange={(e) => updateForm('notifications', { ...form.notifications, slack_webhook_url: e.target.value })} placeholder="https://hooks.slack.com/services/..." className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Channel</label>
            <input type="text" value={form.notifications.slack_channel} onChange={(e) => updateForm('notifications', { ...form.notifications, slack_channel: e.target.value })} placeholder="#ops-alerts" className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition text-sm" />
          </div>
        </div>
      </div>
      <div>
        <h4 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
          <span className="w-5 h-5 rounded bg-orange-500/20 flex items-center justify-center text-[10px] text-orange-400">PD</span>
          PagerDuty
        </h4>
        <div className="space-y-3 pl-1">
          <div>
            <label className="block text-xs text-slate-500 mb-1">API Key</label>
            <input type="password" value={form.notifications.pagerduty_api_key} onChange={(e) => updateForm('notifications', { ...form.notifications, pagerduty_api_key: e.target.value })} className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Service ID</label>
            <input type="text" value={form.notifications.pagerduty_service_id} onChange={(e) => updateForm('notifications', { ...form.notifications, pagerduty_service_id: e.target.value })} placeholder="PXXXXXX" className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition text-sm" />
          </div>
        </div>
      </div>
    </div>
  )

  const renderStepLLM = () => (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Provider</label>
        <select
          value={form.llm.provider}
          onChange={(e) => {
            const provider = e.target.value
            const model = provider === 'anthropic' ? 'claude-sonnet-4-20250514' : 'gpt-4o'
            updateForm('llm', { ...form.llm, provider, model })
          }}
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none transition"
        >
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
        </select>
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">Model Name</label>
        <input type="text" value={form.llm.model} onChange={(e) => updateForm('llm', { ...form.llm, model: e.target.value })} className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white focus:border-blue-500 focus:outline-none transition" />
      </div>
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1">API Key</label>
        <input type="password" value={form.llm.api_key} onChange={(e) => updateForm('llm', { ...form.llm, api_key: e.target.value })} placeholder={form.llm.provider === 'anthropic' ? 'sk-ant-...' : 'sk-...'} className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none transition" />
      </div>
    </div>
  )

  const renderStepReview = () => (
    <div className="space-y-4">
      {/* Summary cards */}
      <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-3">
        <h4 className="text-sm font-medium text-white flex items-center gap-2"><Globe className="w-4 h-4 text-blue-400" /> Basic Info</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <span className="text-slate-500">Name</span><span className="text-slate-300">{form.name || '(not set)'}</span>
          <span className="text-slate-500">Environment</span><span className={clsx('inline-block px-2 py-0.5 rounded text-xs border w-fit', ENV_COLORS[form.environment])}>{form.environment}</span>
        </div>
      </div>
      <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-3">
        <h4 className="text-sm font-medium text-white flex items-center gap-2"><Database className="w-4 h-4 text-green-400" /> Prometheus</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <span className="text-slate-500">URL</span><span className="text-slate-300 break-all">{form.prometheus.url || '(not set)'}</span>
          <span className="text-slate-500">Auth</span><span className="text-slate-300">{form.prometheus.bearer_token ? 'Bearer Token' : form.prometheus.username ? 'Basic Auth' : 'None'}</span>
        </div>
      </div>
      <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-3">
        <h4 className="text-sm font-medium text-white flex items-center gap-2"><Server className="w-4 h-4 text-yellow-400" /> Services ({form.services.filter((s) => s.name).length})</h4>
        <div className="space-y-1">
          {form.services.filter((s) => s.name).map((svc, i) => (
            <div key={i} className="text-sm text-slate-300 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
              {svc.name} <span className="text-slate-500">:{svc.port}</span> <span className="text-slate-600">P99&lt;{svc.slo_latency_p99_ms}ms Err&lt;{svc.slo_error_rate_percent}%</span>
            </div>
          ))}
        </div>
      </div>
      {form.kubernetes.enabled && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-3">
          <h4 className="text-sm font-medium text-white flex items-center gap-2"><Shield className="w-4 h-4 text-purple-400" /> Kubernetes</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <span className="text-slate-500">Cluster</span><span className="text-slate-300">{form.kubernetes.cluster_name || '(not set)'}</span>
            <span className="text-slate-500">Namespace</span><span className="text-slate-300">{form.kubernetes.namespace}</span>
          </div>
        </div>
      )}
      <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-3">
        <h4 className="text-sm font-medium text-white flex items-center gap-2"><Brain className="w-4 h-4 text-pink-400" /> LLM</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <span className="text-slate-500">Provider</span><span className="text-slate-300 capitalize">{form.llm.provider}</span>
          <span className="text-slate-500">Model</span><span className="text-slate-300">{form.llm.model}</span>
          <span className="text-slate-500">API Key</span><span className="text-slate-300">{form.llm.api_key ? '***' + form.llm.api_key.slice(-4) : '(not set)'}</span>
        </div>
      </div>

      {/* Test All Connections */}
      <div className="pt-2">
        <button onClick={handleTestAll} disabled={testingAll} className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg text-sm font-medium transition disabled:opacity-50">
          {testingAll ? <RefreshCw className="w-4 h-4 animate-spin" /> : <TestTube className="w-4 h-4" />}
          Test All Connections
        </button>
      </div>

      {testResults && (
        <div className="bg-slate-900/60 border border-slate-700/50 rounded-lg p-4 space-y-2">
          <h4 className="text-sm font-medium text-white mb-2">Test Results</h4>
          <div className="space-y-1.5">
            <TestRow label="Prometheus" ok={testResults.prometheus_ok} message={testResults.prometheus_message} />
            <TestRow label="Kubernetes" ok={testResults.kubernetes_ok} message={testResults.kubernetes_message} />
            <TestRow label="LLM" ok={testResults.llm_ok} message={testResults.llm_message} />
            {Object.entries(testResults.services_reachable).map(([name, ok]) => (
              <TestRow key={name} label={`Service: ${name}`} ok={ok} message={ok ? 'Reachable' : 'Unreachable'} />
            ))}
          </div>
          <div className={clsx('mt-3 pt-2 border-t border-slate-700/50 text-sm font-medium', testResults.overall_ok ? 'text-green-400' : 'text-red-400')}>
            {testResults.overall_ok ? 'All checks passed' : 'Some checks failed'}
          </div>
        </div>
      )}
    </div>
  )

  const stepRenderers = [
    renderStepBasicInfo,
    renderStepPrometheus,
    renderStepServices,
    renderStepKubernetes,
    renderStepNotifications,
    renderStepLLM,
    renderStepReview,
  ]

  // ─── Main render ────────────────────────────────────────────────

  return (
    <div className="space-y-6 relative">
      {/* Toast */}
      {toast && (
        <div className={clsx('fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg border text-sm font-medium flex items-center gap-2 animate-in slide-in-from-right', toast.type === 'success' ? 'bg-green-900/90 border-green-500/30 text-green-300' : 'bg-red-900/90 border-red-500/30 text-red-300')}>
          {toast.type === 'success' ? <Check className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
          {toast.message}
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-3">
            <Plug className="w-6 h-6 text-blue-400" />
            Connections
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Onboard applications and configure real telemetry sources for the SCL-Governor
          </p>
        </div>
        <button onClick={openNewWizard} className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition shadow-lg shadow-blue-600/20">
          <Plus className="w-4 h-4" />
          Onboard New Application
        </button>
      </div>

      {/* Connection Cards Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-6 h-6 text-slate-500 animate-spin" />
        </div>
      ) : connections.length === 0 ? (
        <div className="text-center py-20">
          <Plug className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-slate-400">No connections yet</h3>
          <p className="text-sm text-slate-500 mt-1">Onboard your first application to start pulling real telemetry</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {connections.map((conn) => {
            const isDemo = conn.id === 'demo-connection'
            const isTesting = testingIds.has(conn.id)
            const status = isTesting ? 'testing' : conn.status
            const st = STATUS_STYLES[status] || STATUS_STYLES.disconnected
            return (
              <div key={conn.id} className={clsx('bg-slate-800/50 border rounded-xl p-5 transition-all hover:border-slate-600', isDemo ? 'border-blue-500/30 ring-1 ring-blue-500/10' : 'border-slate-700/50')}>
                {/* Header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-white font-semibold truncate">{conn.name}</h3>
                      {isDemo && <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30 shrink-0">DEMO</span>}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5 truncate">{conn.description}</p>
                  </div>
                  <span className={clsx('text-[10px] px-2 py-0.5 rounded border shrink-0 ml-2', ENV_COLORS[conn.environment])}>
                    {conn.environment}
                  </span>
                </div>

                {/* Status */}
                <div className="flex items-center gap-2 mb-4">
                  <span className={clsx('w-2 h-2 rounded-full', st.dot)} />
                  <span className="text-xs text-slate-400">{st.label}</span>
                  {conn.last_error && <span className="text-xs text-red-400 truncate ml-auto" title={conn.last_error}>{conn.last_error}</span>}
                </div>

                {/* Metrics */}
                <div className="grid grid-cols-3 gap-2 mb-4">
                  <div className="bg-slate-900/50 rounded-lg p-2 text-center">
                    <div className="text-xs text-slate-500">URL</div>
                    <div className="text-[10px] text-slate-300 truncate mt-0.5" title={conn.prometheus.url}>{conn.prometheus.url || '-'}</div>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-2 text-center">
                    <div className="text-xs text-slate-500">Services</div>
                    <div className="text-sm font-bold text-white mt-0.5">{conn.services.length}</div>
                  </div>
                  <div className="bg-slate-900/50 rounded-lg p-2 text-center">
                    <div className="text-xs text-slate-500">Metrics</div>
                    <div className="text-sm font-bold text-white mt-0.5">{conn.telemetry_metrics_count.toLocaleString()}</div>
                  </div>
                </div>

                {conn.last_telemetry_at && (
                  <div className="text-[10px] text-slate-600 mb-3">
                    Last telemetry: {new Date(conn.last_telemetry_at).toLocaleString()}
                  </div>
                )}

                {/* Actions */}
                <div className="flex items-center gap-2 pt-3 border-t border-slate-700/50">
                  <button onClick={() => handleTest(conn.id)} disabled={isTesting} className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-xs font-medium transition disabled:opacity-50" title="Test Connectivity">
                    {isTesting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <TestTube className="w-3 h-3" />}
                    Test
                  </button>
                  <button onClick={() => handleActivate(conn.id)} className="flex items-center gap-1 px-2.5 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded text-xs font-medium transition" title="Activate for Governor">
                    <Zap className="w-3 h-3" />
                    Activate
                  </button>
                  <button onClick={() => handleEdit(conn)} className="flex items-center gap-1 px-2.5 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-xs font-medium transition" title="Edit">
                    <Pencil className="w-3 h-3" />
                    Edit
                  </button>
                  {!isDemo && (
                    <button onClick={() => handleDelete(conn.id)} className="flex items-center gap-1 px-2.5 py-1.5 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded text-xs font-medium transition ml-auto" title="Delete">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Wizard Modal */}
      {wizardOpen && (
        <div className="fixed inset-0 z-40 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setWizardOpen(false)} />
          <div className="relative bg-slate-800 border border-slate-700/50 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col mx-4">
            {/* Wizard Header */}
            <div className="px-6 pt-5 pb-4 border-b border-slate-700/50">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-white">{editingId ? 'Edit Connection' : 'Onboard New Application'}</h3>
                <button onClick={() => setWizardOpen(false)} className="text-slate-500 hover:text-slate-300 transition">
                  <X className="w-5 h-5" />
                </button>
              </div>
              {/* Progress Bar */}
              <div className="flex items-center gap-1">
                {STEPS.map((s, i) => {
                  const Icon = s.icon
                  return (
                    <button
                      key={i}
                      onClick={() => setStep(i)}
                      className={clsx(
                        'flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-all',
                        i === step ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : i < step ? 'bg-green-600/10 text-green-400' : 'text-slate-500 hover:text-slate-400'
                      )}
                    >
                      <Icon className="w-3 h-3" />
                      <span className="hidden sm:inline">{s.label}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Wizard Content */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              <h4 className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                {(() => { const Icon = STEPS[step].icon; return <Icon className="w-4 h-4 text-blue-400" /> })()}
                Step {step + 1}: {STEPS[step].label}
              </h4>
              {stepRenderers[step]()}
            </div>

            {/* Wizard Footer */}
            <div className="px-6 py-4 border-t border-slate-700/50 flex items-center justify-between">
              <button
                onClick={() => setStep((s) => Math.max(0, s - 1))}
                disabled={step === 0}
                className="flex items-center gap-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium transition disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              <div className="flex items-center gap-2">
                {step === STEPS.length - 1 ? (
                  <button
                    onClick={handleSaveActivate}
                    disabled={saving}
                    className="flex items-center gap-2 px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition disabled:opacity-50 shadow-lg shadow-blue-600/20"
                  >
                    {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                    Save & Activate
                  </button>
                ) : (
                  <button
                    onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
                    className="flex items-center gap-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-medium transition"
                  >
                    Next <ArrowRight className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TestRow({ label, ok, message }: { label: string; ok: boolean; message: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {ok ? <Check className="w-4 h-4 text-green-400 shrink-0" /> : <X className="w-4 h-4 text-red-400 shrink-0" />}
      <span className="text-slate-300 font-medium">{label}</span>
      <span className={clsx('text-xs ml-auto', ok ? 'text-green-500' : 'text-red-500')}>{message}</span>
    </div>
  )
}
