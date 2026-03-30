import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  RefreshCw,
  Activity,
  TrendingUp,
  FlaskConical,
  Brain,
  GraduationCap,
  Settings,
  Cpu,
  Plug,
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/control-loop', label: 'Control Loop', icon: RefreshCw },
  { to: '/telemetry', label: 'Telemetry', icon: Activity },
  { to: '/predictions', label: 'Predictions', icon: TrendingUp },
  { to: '/simulations', label: 'Simulations', icon: FlaskConical },
  { to: '/decisions', label: 'Decisions', icon: Brain },
  { to: '/learning', label: 'Learning', icon: GraduationCap },
  { to: '/connections', label: 'Connections', icon: Plug },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="w-[250px] bg-slate-800 border-r border-slate-700/50 flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center gap-3 px-5 border-b border-slate-700/50">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <Cpu className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="text-sm font-bold text-white tracking-wide">SCL-Governor</div>
          <div className="text-[10px] text-slate-500 uppercase tracking-widest">Control Loop</div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
              )
            }
          >
            <item.icon className="w-[18px] h-[18px]" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-slate-700/50">
        <div className="text-[10px] text-slate-600 text-center">
          LLM-Supervised Control Loops v1.0
        </div>
      </div>
    </aside>
  )
}
