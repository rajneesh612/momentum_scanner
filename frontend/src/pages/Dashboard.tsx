// Basic dashboard: sync a symbol's price history from Yahoo Finance via the
// backend, then load and display what's stored in Postgres.
//
// Future pages to build alongside this one: stock list, stock detail,
// momentum ranking, watchlist, charts.

import { useEffect, useState } from 'react'

import PriceChart from '../components/PriceChart'
import PriceHistoryTable from '../components/PriceHistoryTable'
import StockCombobox from '../components/StockCombobox'
import { ApiError, getHealth, getStockHistory, syncSymbolHistory } from '../services/api'
import type { Interval, PriceHistoryPoint } from '../types'

function isoDate(daysAgo: number): string {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}

const INTERVALS: { id: Interval; label: string }[] = [
  { id: '1d', label: 'Daily' },
  { id: '1wk', label: 'Weekly' },
  { id: '1mo', label: 'Monthly' },
]

const RANGE_PRESETS: { label: string; years: number }[] = [
  { label: '1Y', years: 1 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: 10 },
]

export default function Dashboard() {
  const [backendStatus, setBackendStatus] = useState('Unknown')
  const [symbol, setSymbol] = useState('RELIANCE.NS')
  const [startDate, setStartDate] = useState(isoDate(30))
  const [endDate, setEndDate] = useState(isoDate(0))
  const [interval, setSelectedInterval] = useState<Interval>('1d')
  const [prices, setPrices] = useState<PriceHistoryPoint[]>([])
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSyncing, setIsSyncing] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    getHealth()
      .then((health) => setBackendStatus(health.status))
      .catch(() => setBackendStatus('Unreachable'))
  }, [])

  async function handleSync() {
    setIsSyncing(true)
    setErrorMessage(null)
    setStatusMessage(null)
    try {
      const result = await syncSymbolHistory(symbol, startDate, endDate, interval)
      setStatusMessage(
        `Synced ${result.symbol}: ${result.records_created} new, ` +
          `${result.records_skipped} already stored (${result.records_fetched} fetched).`,
      )
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : 'Sync failed.')
    } finally {
      setIsSyncing(false)
    }
  }

  async function handleLoadHistory() {
    setIsLoading(true)
    setErrorMessage(null)
    setStatusMessage(null)
    try {
      const result = await getStockHistory(symbol, startDate, endDate, interval)
      setPrices(result.prices)
    } catch (error) {
      setPrices([])
      setErrorMessage(error instanceof ApiError ? error.message : 'Failed to load history.')
    } finally {
      setIsLoading(false)
    }
  }

  const statusColor = backendStatus === 'ok' ? 'text-emerald-400' : 'text-amber-400'

  return (
    <main className="px-6 py-10">
      <div className="mx-auto flex max-w-4xl flex-col gap-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold">Momentum Stock Scanner</h1>
          <p className="text-sm text-slate-400">
            Backend status: <span className={`font-mono ${statusColor}`}>{backendStatus}</span>
          </p>
        </header>

        <section className="flex flex-col gap-4 rounded-lg border border-slate-800 bg-slate-900/40 p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-5">
            <label htmlFor="symbol" className="flex flex-col gap-1 text-sm sm:col-span-2">
              Symbol
              <StockCombobox id="symbol" value={symbol} onSelect={setSymbol} placeholder="Search by name or symbol…" />
            </label>
            <label htmlFor="interval" className="flex flex-col gap-1 text-sm">
              Interval
              <select
                id="interval"
                value={interval}
                onChange={(e) => setSelectedInterval(e.target.value as Interval)}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              >
                {INTERVALS.map(({ id, label }) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="start-date" className="flex flex-col gap-1 text-sm">
              Start date
              <input
                id="start-date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />
            </label>
            <label htmlFor="end-date" className="flex flex-col gap-1 text-sm">
              End date
              <input
                id="end-date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500">Quick range:</span>
            {RANGE_PRESETS.map(({ label, years }) => (
              <button
                key={label}
                type="button"
                onClick={() => {
                  setStartDate(isoDate(years * 365))
                  setEndDate(isoDate(0))
                }}
                className="rounded-full border border-slate-700 px-2.5 py-1 text-slate-300 transition hover:border-slate-500 hover:text-slate-100"
              >
                {label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleSync}
              disabled={isSyncing || !symbol}
              className="rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isSyncing ? 'Syncing…' : 'Sync from Yahoo Finance'}
            </button>
            <button
              type="button"
              onClick={handleLoadHistory}
              disabled={isLoading || !symbol}
              className="rounded-md border border-slate-700 px-4 py-2 text-sm font-medium text-slate-100 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? 'Loading…' : 'Load history'}
            </button>
          </div>

          {statusMessage && <p className="text-sm text-emerald-400">{statusMessage}</p>}
          {errorMessage && <p className="text-sm text-rose-400">{errorMessage}</p>}
        </section>

        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-medium text-slate-200">
            Price history
            {prices.length > 0 && <span className="ml-2 text-slate-500">({prices.length} rows)</span>}
          </h2>
          {prices.length > 0 ? (
            <>
              <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                <PriceChart symbol={symbol} prices={prices} />
              </div>
              <PriceHistoryTable prices={prices} />
            </>
          ) : (
            <p className="text-sm text-slate-500">No data loaded yet. Sync a symbol, then load its history.</p>
          )}
        </section>
      </div>
    </main>
  )
}
