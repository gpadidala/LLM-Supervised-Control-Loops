import { ReactNode } from 'react'
import Sidebar from './Sidebar'
import RegimeBadge from './RegimeBadge'
import { useSCLStore } from '@/store/scl.store'
import { Activity, Wifi, WifiOff } from 'lucide-react'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { status, ws } = useSCLStore()
  const isConnected = ws !== null && ws.readyState === WebSocket.OPEN

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="h-14 bg-slate-800/80 border-b border-slate-700/50 flex items-center justify-between px-6 backdrop-blur-sm flex-shrink-0">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold text-slate-200">
              SCL-Governor
            </h1>
            {status ? (
              <RegimeBadge regime={status.current_regime} />
            ) : (
              <span className="px-3 py-1 rounded-full text-xs font-medium bg-slate-700 text-slate-400">
                Connecting...
              </span>
            )}
            {!status?.is_running && (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-amber-500/20 text-amber-400 border border-amber-500/30">
                Demo Mode
              </span>
            )}
          </div>
          <div className="flex items-center gap-4">
            {status && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Activity className="w-4 h-4" />
                <span>Cycle #{status.cycle_count}</span>
                <span className="text-slate-600">|</span>
                <span>
                  Uptime: {formatUptime(status.uptime_seconds)}
                </span>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              {isConnected ? (
                <Wifi className="w-4 h-4 text-green-400" />
              ) : (
                <WifiOff className="w-4 h-4 text-red-400" />
              )}
              <span className={`text-xs ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
                {isConnected ? 'Live' : 'Disconnected'}
              </span>
            </div>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 overflow-auto p-6 bg-slate-900">
          {children}
        </main>
      </div>
    </div>
  )
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}
