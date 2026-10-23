import { useState } from 'react'

import Backtest from './pages/Backtest'
import Dashboard from './pages/Dashboard'
import Signals from './pages/Signals'

type Tab = 'data' | 'backtest' | 'signals'

const TABS: { id: Tab; label: string }[] = [
  { id: 'data', label: 'Data' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'signals', label: 'Scanner' },
]

function App() {
  const [tab, setTab] = useState<Tab>('data')

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <nav className="border-b border-slate-800">
        <div className="mx-auto flex max-w-4xl gap-1 px-6 pt-3">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded-t-md px-3 py-2 text-sm font-medium transition ${
                tab === id
                  ? 'border border-b-0 border-slate-800 bg-slate-900/40 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>
      {tab === 'data' && <Dashboard />}
      {tab === 'backtest' && <Backtest />}
      {tab === 'signals' && <Signals />}
    </div>
  )
}

export default App
