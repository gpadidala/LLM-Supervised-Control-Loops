import { Routes, Route } from 'react-router-dom'
import { useEffect } from 'react'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import ControlLoop from './pages/ControlLoop'
import Telemetry from './pages/Telemetry'
import Predictions from './pages/Predictions'
import Simulations from './pages/Simulations'
import Decisions from './pages/Decisions'
import Learning from './pages/Learning'
import Connections from './pages/Connections'
import Settings from './pages/Settings'
import { useSCLStore } from './store/scl.store'

export default function App() {
  const { connectWs, fetchStatus, fetchCycles } = useSCLStore()

  useEffect(() => {
    fetchStatus()
    fetchCycles()
    connectWs()

    const interval = setInterval(() => {
      fetchStatus()
    }, 10000)

    return () => clearInterval(interval)
  }, [connectWs, fetchStatus, fetchCycles])

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/control-loop" element={<ControlLoop />} />
        <Route path="/telemetry" element={<Telemetry />} />
        <Route path="/predictions" element={<Predictions />} />
        <Route path="/simulations" element={<Simulations />} />
        <Route path="/decisions" element={<Decisions />} />
        <Route path="/learning" element={<Learning />} />
        <Route path="/connections" element={<Connections />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </Layout>
  )
}
