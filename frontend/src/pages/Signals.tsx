// Daily NIFTY 500 hybrid scanner view: latest BUY/SELL signals, the most
// recent scan run's data-quality summary, and manual troubleshooting
// controls (trigger a scan, send a Telegram test) gated behind the same
// X-Scan-Api-Key the backend requires - entered here, kept only in this
// page's local state (never persisted), never logged.

import { useEffect, useState } from 'react'

import {
  ApiError,
  getLatestScan,
  getLatestSignals,
  getStrategyConfig,
  sendTelegramTest,
  triggerManualScan,
} from '../services/api'
import type { ManualScanResponse, ScanRun, SignalEvent, StrategyConfig } from '../types'

const priceFormatter = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })

function SignalBadge({ type }: { type: SignalEvent['signal_type'] }) {
  const classes =
    type === 'BUY'
      ? 'border-emerald-700/60 bg-emerald-900/30 text-emerald-400'
      : 'border-rose-700/60 bg-rose-900/30 text-rose-400'
  return (
    <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase ${classes}`}>
      {type}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'success'
      ? 'text-emerald-400'
      : status === 'partial_failure'
        ? 'text-amber-400'
        : status === 'failed'
          ? 'text-rose-400'
          : 'text-slate-400'
  return <span className={`font-medium ${tone}`}>{status}</span>
}

export default function Signals() {
  const [signals, setSignals] = useState<SignalEvent[]>([])
  const [latestScan, setLatestScan] = useState<ScanRun | null>(null)
  const [config, setConfig] = useState<StrategyConfig | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const [apiKey, setApiKey] = useState('')
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [isRunningScan, setIsRunningScan] = useState(false)
  const [isTestingTelegram, setIsTestingTelegram] = useState(false)
  const [scanResult, setScanResult] = useState<ManualScanResponse | null>(null)

  async function loadAll() {
    setIsLoading(true)
    setErrorMessage(null)
    try {
      const [signalsResponse, scan, strategyConfig] = await Promise.all([
        getLatestSignals(50),
        getLatestScan(),
        getStrategyConfig(),
      ])
      setSignals(signalsResponse.items)
      setLatestScan(scan)
      setConfig(strategyConfig)
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : 'Failed to load scanner data.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  async function handleManualScan() {
    setIsRunningScan(true)
    setActionMessage(null)
    setScanResult(null)
    try {
      const result = await triggerManualScan(apiKey)
      setScanResult(result)
      setActionMessage(`Scan ${result.status}: ${result.buy_signals} BUY, ${result.sell_signals} SELL.`)
      await loadAll()
    } catch (error) {
      setActionMessage(error instanceof ApiError ? `Scan failed: ${error.message}` : 'Scan failed.')
    } finally {
      setIsRunningScan(false)
    }
  }

  async function handleTelegramTest() {
    setIsTestingTelegram(true)
    setActionMessage(null)
    try {
      const result = await sendTelegramTest(apiKey)
      setActionMessage(
        result.success ? 'Telegram test message sent.' : `Telegram test failed: ${result.error}`,
      )
    } catch (error) {
      setActionMessage(error instanceof ApiError ? `Telegram test failed: ${error.message}` : 'Telegram test failed.')
    } finally {
      setIsTestingTelegram(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-6 py-6">
      <section>
        <h2 className="text-lg font-semibold text-slate-100">Daily Scanner</h2>
        <p className="mt-1 text-sm text-slate-400">
          Hybrid trend/momentum/volume strategy over the NIFTY 500 universe. Research and
          decision-support only - not a trading recommendation, and nothing here places a live
          order.
        </p>
        {config && (
          <p className="mt-2 text-xs text-slate-500">
            Strategy: {config.name} {config.version} - Close &gt; SMA{config.sma_mid} &gt; SMA
            {config.sma_long}, {config.momentum_short_days}-session &amp; ~12-month momentum
            positive, volume &gt; {config.volume_multiplier}x {config.volume_lookback}-day average.
          </p>
        )}
      </section>

      {latestScan && (
        <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 text-sm">
          <h3 className="font-medium text-slate-200">Latest scan</h3>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-slate-400 sm:grid-cols-4">
            <div>
              <dt className="text-xs uppercase text-slate-500">Status</dt>
              <dd>
                <StatusBadge status={latestScan.status} />
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Session</dt>
              <dd className="font-mono text-slate-300">{latestScan.session_date}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Universe</dt>
              <dd>{latestScan.universe_size}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">BUY / SELL</dt>
              <dd>
                <span className="text-emerald-400">{latestScan.buy_signals}</span> /{' '}
                <span className="text-rose-400">{latestScan.sell_signals}</span>
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Succeeded</dt>
              <dd>{latestScan.symbols_succeeded}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Stale</dt>
              <dd>{latestScan.symbols_stale}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Skipped</dt>
              <dd>{latestScan.symbols_skipped}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase text-slate-500">Failed</dt>
              <dd>{latestScan.symbols_failed}</dd>
            </div>
          </dl>
          {latestScan.error_message && (
            <p className="mt-2 text-xs text-rose-400">{latestScan.error_message}</p>
          )}
        </section>
      )}

      <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h3 className="text-sm font-medium text-slate-200">Troubleshooting</h3>
        <p className="mt-1 text-xs text-slate-500">
          Requires the backend&apos;s configured SCAN_API_KEY. Never stored beyond this page.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="X-Scan-Api-Key"
            className="rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-600"
          />
          <button
            type="button"
            onClick={handleManualScan}
            disabled={isRunningScan || !apiKey}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 disabled:opacity-50"
          >
            {isRunningScan ? 'Scanning…' : 'Run scan now'}
          </button>
          <button
            type="button"
            onClick={handleTelegramTest}
            disabled={isTestingTelegram || !apiKey}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 transition hover:border-slate-500 disabled:opacity-50"
          >
            {isTestingTelegram ? 'Sending…' : 'Send Telegram test'}
          </button>
        </div>
        {actionMessage && <p className="mt-2 text-xs text-slate-400">{actionMessage}</p>}
        {scanResult && scanResult.data_quality_report.length > 0 && (
          <div className="mt-3 max-h-48 overflow-y-auto rounded-md border border-slate-800 text-xs">
            <table className="w-full">
              <thead className="bg-slate-900 text-left text-slate-500">
                <tr>
                  <th className="px-2 py-1">Symbol</th>
                  <th className="px-2 py-1">Status</th>
                  <th className="px-2 py-1">Signal</th>
                  <th className="px-2 py-1">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {scanResult.data_quality_report.map((o) => (
                  <tr key={o.symbol}>
                    <td className="px-2 py-1 font-mono text-slate-300">{o.symbol}</td>
                    <td className="px-2 py-1 text-slate-400">{o.status}</td>
                    <td className="px-2 py-1 text-slate-400">{o.signal_type ?? '—'}</td>
                    <td className="px-2 py-1 text-rose-400">{o.error ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h3 className="text-sm font-medium text-slate-200">Latest signals</h3>
        {isLoading && <p className="mt-2 text-sm text-slate-500">Loading…</p>}
        {errorMessage && <p className="mt-2 text-sm text-rose-400">{errorMessage}</p>}
        {!isLoading && signals.length === 0 && !errorMessage && (
          <p className="mt-2 text-sm text-slate-500">
            No signals yet - run a scan, or wait for the next scheduled one.
          </p>
        )}
        {signals.length > 0 && (
          <div className="mt-2 overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="bg-slate-900 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-2 font-medium">Signal</th>
                  <th className="px-4 py-2 font-medium">Symbol</th>
                  <th className="px-4 py-2 font-medium">Session</th>
                  <th className="px-4 py-2 text-right font-medium">Price</th>
                  <th className="px-4 py-2 font-medium">Data quality</th>
                  <th className="px-4 py-2 font-medium">Notification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {signals.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-900/50">
                    <td className="px-4 py-2">
                      <SignalBadge type={s.signal_type} />
                    </td>
                    <td className="px-4 py-2 font-mono text-slate-300">{s.symbol}</td>
                    <td className="px-4 py-2 font-mono text-slate-400">{s.session_date}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-slate-300">
                      ₹{priceFormatter.format(s.price)}
                    </td>
                    <td className="px-4 py-2 text-slate-400">{s.data_quality_status}</td>
                    <td className="px-4 py-2 text-slate-400">{s.notification_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
