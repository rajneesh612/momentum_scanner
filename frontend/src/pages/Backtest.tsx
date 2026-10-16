// Momentum strategy backtester: runs a long-only SMA-crossover strategy
// against previously-synced price history and visualizes the result.
//
// This is a historical simulation, not a prediction or guarantee of
// future returns — every piece of copy on this page should keep that
// framing, and every number shown must come straight from the API
// response (never fabricated/sample data).

import { useState } from 'react'

import ChartErrorBoundary from '../components/ChartErrorBoundary'
import EquityCurveChart from '../components/EquityCurveChart'
import EventDetailPanel from '../components/EventDetailPanel'
import PriceSmaChart from '../components/PriceSmaChart'
import StockCombobox from '../components/StockCombobox'
import TradesTable from '../components/TradesTable'
import { ApiError, listStockEvents, runBacktest } from '../services/api'
import type { BacktestResponse, Interval, StockEvent } from '../types'
import { EVENT_CATEGORIES } from '../utils/eventCategories'

function isoDate(daysAgo: number): string {
  const d = new Date()
  d.setDate(d.getDate() - daysAgo)
  return d.toISOString().slice(0, 10)
}

const currencyFormatter = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const percentFormatter = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`

function formatCurrency(value: number): string {
  return `₹${currencyFormatter.format(value)}`
}

function formatSignedCurrency(value: number): string {
  return `${value >= 0 ? '+' : '-'}₹${currencyFormatter.format(Math.abs(value))}`
}

const INTERVALS: { id: Interval; label: string; barLabel: string; short: number; long: number }[] = [
  { id: '1d', label: 'Daily', barLabel: 'days', short: 50, long: 200 },
  { id: '1wk', label: 'Weekly', barLabel: 'weeks', short: 10, long: 40 },
  { id: '1mo', label: 'Monthly', barLabel: 'months', short: 3, long: 12 },
]

const RANGE_PRESETS: { label: string; years: number }[] = [
  { label: '1Y', years: 1 },
  { label: '5Y', years: 5 },
  { label: '10Y', years: 10 },
]

interface StatTileProps {
  label: string
  value: string
  sublabel?: string
  tone?: 'positive' | 'negative' | 'neutral'
}

function StatTile({ label, value, sublabel, tone = 'neutral' }: StatTileProps) {
  const toneClass =
    tone === 'positive' ? 'text-emerald-400' : tone === 'negative' ? 'text-rose-400' : 'text-slate-100'
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={`text-lg font-semibold ${toneClass}`}>{value}</span>
      {sublabel && <span className="text-xs text-slate-500">{sublabel}</span>}
    </div>
  )
}

export default function Backtest() {
  const [symbol, setSymbol] = useState('RELIANCE.NS')
  const [startDate, setStartDate] = useState(isoDate(365))
  const [endDate, setEndDate] = useState(isoDate(0))
  const [interval, setSelectedInterval] = useState<Interval>('1d')
  const [shortWindow, setShortWindow] = useState(50)
  const [longWindow, setLongWindow] = useState(200)
  const [initialCapital, setInitialCapital] = useState(100000)
  const [result, setResult] = useState<BacktestResponse | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isRunning, setIsRunning] = useState(false)

  const [events, setEvents] = useState<StockEvent[]>([])
  const [newsUnavailable, setNewsUnavailable] = useState(false)
  const [eventCategoryFilter, setEventCategoryFilter] = useState('')
  const [selectedEventCluster, setSelectedEventCluster] = useState<StockEvent[] | null>(null)

  function handleIntervalChange(next: Interval) {
    setSelectedInterval(next)
    const defaults = INTERVALS.find((i) => i.id === next)
    if (defaults) {
      setShortWindow(defaults.short)
      setLongWindow(defaults.long)
    }
  }

  async function fetchEvents(category: string) {
    setSelectedEventCluster(null)
    try {
      const response = await listStockEvents(symbol, {
        startDate,
        endDate,
        category: category || undefined,
      })
      setEvents(response.events)
      setNewsUnavailable(response.news_unavailable)
    } catch {
      // The investment chart must keep working even if news is down.
      setEvents([])
      setNewsUnavailable(true)
    }
  }

  async function handleRun() {
    setIsRunning(true)
    setErrorMessage(null)
    try {
      const response = await runBacktest(symbol, {
        startDate,
        endDate,
        shortWindow,
        longWindow,
        initialCapital,
        interval,
      })
      setResult(response)
      await fetchEvents(eventCategoryFilter)
    } catch (error) {
      setResult(null)
      setErrorMessage(error instanceof ApiError ? error.message : 'Backtest failed.')
    } finally {
      setIsRunning(false)
    }
  }

  async function handleEventCategoryChange(category: string) {
    setEventCategoryFilter(category)
    if (result) await fetchEvents(category)
  }

  const summary = result?.summary
  const barLabel = INTERVALS.find((i) => i.id === interval)?.barLabel ?? 'bars'

  // Derived, not invented: every value below comes straight from `summary`
  // / `result` fields already in the API response.
  const profitLoss = summary ? summary.final_equity - summary.initial_capital : 0
  const buyAndHoldFinalValue = summary
    ? summary.initial_capital * (1 + summary.buy_and_hold_return_pct / 100)
    : 0
  const vsBuyAndHold = summary ? summary.final_equity - buyAndHoldFinalValue : 0
  const beatBuyAndHold = vsBuyAndHold >= 0

  return (
    <main className="px-6 py-10">
      <div className="mx-auto flex max-w-4xl flex-col gap-8">
        <header className="flex flex-col gap-1">
          <h1 className="text-3xl font-semibold">Momentum Backtester</h1>
          <p className="text-sm text-slate-400">
            Long-only SMA crossover: go long when the short average crosses above the long
            average, exit when it crosses back below.
          </p>
          <p className="text-xs text-amber-400">
            This is a historical simulation, not a prediction or guarantee of future investment
            returns.
          </p>
        </header>

        <section className="flex flex-col gap-4 rounded-lg border border-slate-800 bg-slate-900/40 p-5">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-6">
            <label htmlFor="bt-symbol" className="flex flex-col gap-1 text-sm sm:col-span-2">
              Symbol
              <StockCombobox id="bt-symbol" value={symbol} onSelect={setSymbol} placeholder="Search by name or symbol…" />
            </label>
            <label htmlFor="bt-interval" className="flex flex-col gap-1 text-sm sm:col-span-2">
              Interval
              <select
                id="bt-interval"
                value={interval}
                onChange={(e) => handleIntervalChange(e.target.value as Interval)}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              >
                {INTERVALS.map(({ id, label }) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor="bt-start" className="flex flex-col gap-1 text-sm">
              Start date
              <input
                id="bt-start"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />
            </label>
            <label htmlFor="bt-end" className="flex flex-col gap-1 text-sm">
              End date
              <input
                id="bt-end"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />
            </label>

            <label htmlFor="bt-short" className="flex flex-col gap-1 text-sm sm:col-span-2">
              Short SMA ({barLabel})
              <input
                id="bt-short"
                type="number"
                min={1}
                value={shortWindow}
                onChange={(e) => setShortWindow(Number(e.target.value))}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 tabular-nums outline-none focus:border-slate-500"
              />
            </label>
            <label htmlFor="bt-long" className="flex flex-col gap-1 text-sm sm:col-span-2">
              Long SMA ({barLabel})
              <input
                id="bt-long"
                type="number"
                min={2}
                value={longWindow}
                onChange={(e) => setLongWindow(Number(e.target.value))}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 tabular-nums outline-none focus:border-slate-500"
              />
            </label>
            <label htmlFor="bt-capital" className="flex flex-col gap-1 text-sm sm:col-span-2">
              Initial capital (₹)
              <input
                id="bt-capital"
                type="number"
                min={1}
                step={1000}
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                className="rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 tabular-nums outline-none focus:border-slate-500"
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

          <div>
            <button
              type="button"
              onClick={handleRun}
              disabled={isRunning || !symbol || shortWindow >= longWindow}
              className="rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isRunning ? 'Running…' : 'Run backtest'}
            </button>
            {shortWindow >= longWindow && (
              <span className="ml-3 text-xs text-amber-400">Short SMA must be less than long SMA.</span>
            )}
          </div>

          {errorMessage && <p className="text-sm text-rose-400">{errorMessage}</p>}
        </section>

        {result && summary && (
          <>
            {!result.is_fully_warmed_up && (
              <div className="rounded-md border border-amber-700/60 bg-amber-900/20 px-4 py-3 text-sm text-amber-300">
                <p className="font-medium">Limited history — treat these results with caution</p>
                <p className="mt-1 text-xs text-amber-400/90">
                  The {result.long_window}-{barLabel} average needs {result.long_window} {barLabel}
                  {' '}of prior data to be reliable. Only {result.lookback_bars} {barLabel} were found
                  before the start date
                  {result.warmup_complete_date
                    ? `, so the signal wasn't valid until ${result.warmup_complete_date}.`
                    : ', and it never became valid during this window — the strategy ran flat the whole time.'}
                  {' '}We automatically tried to fetch more history for you; if this persists, try an
                  earlier start date, a shorter long-average window, or sync more history on the
                  Data tab.
                </p>
              </div>
            )}

            {result.is_fully_warmed_up && summary.num_trades === 0 && (
              <div className="rounded-md border border-slate-700 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
                The short and long averages never crossed in this period — see the Stock Price &amp;
                SMA Signals chart below — so the strategy made no trades and your capital stayed in
                cash the whole time. This is a valid result, not an error.
              </div>
            )}

            <section className="flex flex-col gap-4 rounded-lg border border-slate-800 bg-slate-900/40 p-5">
              <div className="flex flex-col gap-1">
                <span className="text-xs text-slate-500">Your portfolio</span>
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-3xl font-semibold text-slate-100">
                    {formatCurrency(summary.final_equity)}
                  </span>
                  <span className={`text-lg font-medium ${profitLoss >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {formatSignedCurrency(profitLoss)} ({percentFormatter(summary.total_return_pct)})
                  </span>
                </div>
                <span className="text-xs text-slate-500">
                  Started at {formatCurrency(summary.initial_capital)} on {result.start_date}, ended{' '}
                  {result.end_date}.
                </span>
              </div>

              <p className="text-sm text-slate-300">
                Your portfolio ended at {formatCurrency(summary.final_equity)}, a change of{' '}
                {formatSignedCurrency(profitLoss)} ({percentFormatter(summary.total_return_pct)}) from
                your {formatCurrency(summary.initial_capital)} starting investment. Buy &amp; Hold
                ended at {formatCurrency(buyAndHoldFinalValue)} ({percentFormatter(summary.buy_and_hold_return_pct)}
                ). The strategy finished {formatCurrency(Math.abs(vsBuyAndHold))}{' '}
                {beatBuyAndHold ? 'above' : 'below'} Buy &amp; Hold at the end date.
              </p>

              <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <StatTile
                  label="Initial investment"
                  value={formatCurrency(summary.initial_capital)}
                />
                <StatTile
                  label="Final value"
                  value={formatCurrency(summary.final_equity)}
                  tone={profitLoss >= 0 ? 'positive' : 'negative'}
                />
                <StatTile
                  label="Profit / loss"
                  value={formatSignedCurrency(profitLoss)}
                  sublabel={percentFormatter(summary.total_return_pct)}
                  tone={profitLoss >= 0 ? 'positive' : 'negative'}
                />
                <StatTile
                  label="Buy & hold final value"
                  value={formatCurrency(buyAndHoldFinalValue)}
                  sublabel={percentFormatter(summary.buy_and_hold_return_pct)}
                  tone={summary.buy_and_hold_return_pct >= 0 ? 'positive' : 'negative'}
                />
                <StatTile
                  label="Vs. Buy & hold"
                  value={formatSignedCurrency(vsBuyAndHold)}
                  sublabel={beatBuyAndHold ? 'Strategy ahead' : 'Strategy behind'}
                  tone={beatBuyAndHold ? 'positive' : 'negative'}
                />
                <StatTile label="Max drawdown" value={percentFormatter(summary.max_drawdown_pct)} tone="negative" />
                <StatTile label="Trades" value={String(summary.num_trades)} />
                <StatTile label="Win rate" value={`${summary.win_rate_pct.toFixed(0)}%`} />
                <StatTile label="CAGR" value={percentFormatter(summary.cagr_pct)} tone={summary.cagr_pct >= 0 ? 'positive' : 'negative'} />
              </section>

              <p className="text-xs text-slate-500">
                This simulation does not include brokerage, taxes, or slippage — real-world returns
                would likely be lower. Trades are simulated as executing at the same closing price
                that generated the signal, a common backtesting simplification; real execution
                timing may differ.
              </p>
            </section>

            <section className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <label htmlFor="event-category" className="flex items-center gap-1.5 text-slate-500">
                  News category:
                  <select
                    id="event-category"
                    value={eventCategoryFilter}
                    onChange={(e) => handleEventCategoryChange(e.target.value)}
                    className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-slate-200 outline-none focus:border-slate-500"
                  >
                    <option value="">All categories</option>
                    {EVENT_CATEGORIES.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
                {events.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-500">
                    {[...new Set(events.map((e) => e.category))].map((cat) => {
                      const meta = EVENT_CATEGORIES.find((c) => c.id === cat)
                      return (
                        <span key={cat} className="flex items-center gap-1">
                          <span
                            className="h-1.5 w-1.5 rounded-full"
                            style={{ backgroundColor: meta?.color ?? '#94a3b8' }}
                          />
                          {meta?.label ?? cat}
                        </span>
                      )
                    })}
                  </div>
                )}
              </div>

              {events.length === 0 && (
                <div className="rounded-md border border-dashed border-slate-800 px-3 py-2 text-xs text-slate-500">
                  {newsUnavailable ? (
                    <>
                      No corporate announcements were found for{' '}
                      <span className="font-mono">{symbol}</span> — either NSE has no recent
                      announcements on file for this symbol, or the live fetch failed transiently
                      (e.g. rate limiting). Try again in a moment, or a different symbol.
                    </>
                  ) : (
                    <>
                      No events match {eventCategoryFilter ? 'this category' : 'the selected date range'}{' '}
                      for <span className="font-mono">{symbol}</span>. Try a wider date range or a
                      different category.
                    </>
                  )}
                </div>
              )}

              <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                <ChartErrorBoundary chartName="the Stock Price & SMA Signals chart">
                  <PriceSmaChart
                    equityCurve={result.equity_curve}
                    trades={result.trades}
                    shortWindow={result.short_window}
                    longWindow={result.long_window}
                    barLabel={barLabel}
                    events={events}
                    onEventMarkerClick={setSelectedEventCluster}
                  />
                </ChartErrorBoundary>
              </div>

              <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
                <ChartErrorBoundary chartName="the Investment Growth chart">
                  <EquityCurveChart
                    equityCurve={result.equity_curve}
                    trades={result.trades}
                    initialCapital={summary.initial_capital}
                    events={events}
                    onEventMarkerClick={setSelectedEventCluster}
                  />
                </ChartErrorBoundary>
              </div>

              {selectedEventCluster && (
                <EventDetailPanel
                  symbol={symbol}
                  events={selectedEventCluster}
                  onClose={() => setSelectedEventCluster(null)}
                />
              )}
            </section>

            <section className="flex flex-col gap-3">
              <h2 className="text-lg font-medium text-slate-200">
                Trades
                {result.trades.length > 0 && (
                  <span className="ml-2 text-slate-500">({result.trades.length})</span>
                )}
              </h2>
              <TradesTable trades={result.trades} equityCurve={result.equity_curve} />
            </section>
          </>
        )}
      </div>
    </main>
  )
}
