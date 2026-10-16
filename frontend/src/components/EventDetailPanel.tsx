import { useEffect, useState } from 'react'

import { ApiError, getEventImpact } from '../services/api'
import type { EventImpactResponse, StockEvent } from '../types'
import { categoryColor, categoryLabel } from '../utils/eventCategories'

interface EventDetailPanelProps {
  symbol: string
  events: StockEvent[]
  onClose: () => void
}

const dateTimeFormatter = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
  timeZoneName: 'short',
})

const WINDOW_LABELS: Record<number, string> = {
  1: '1 day',
  5: '5 days',
  20: '20 days',
  60: '60 days',
  120: '120 days',
}

function formatPercent(value: number | null): string {
  if (value === null) return '—'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function toneClass(value: number | null): string {
  if (value === null) return 'text-slate-500'
  return value >= 0 ? 'text-emerald-400' : 'text-rose-400'
}

export default function EventDetailPanel({ symbol, events, onClose }: EventDetailPanelProps) {
  const [selected, setSelected] = useState<StockEvent | null>(events.length === 1 ? events[0] : null)
  const [impact, setImpact] = useState<EventImpactResponse | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!selected) return
    setImpact(null)
    setErrorMessage(null)
    setIsLoading(true)
    getEventImpact(symbol, selected.id)
      .then(setImpact)
      .catch((error) => {
        setErrorMessage(error instanceof ApiError ? error.message : 'Could not load impact data.')
      })
      .finally(() => setIsLoading(false))
  }, [symbol, selected])

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-sm font-medium text-slate-200">
          {events.length > 1 && !selected ? `${events.length} events on this date` : 'Event detail'}
        </h3>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-slate-500 transition hover:text-slate-200"
        >
          Close ✕
        </button>
      </div>

      {!selected && (
        <ul className="flex flex-col gap-1">
          {events.map((event) => (
            <li key={event.id}>
              <button
                type="button"
                onClick={() => setSelected(event)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-slate-300 hover:bg-slate-800"
              >
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: categoryColor(event.category) }}
                />
                <span className="truncate">{event.title}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <>
          {events.length > 1 && (
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="self-start text-xs text-slate-500 hover:text-slate-300"
            >
              ← Back to list
            </button>
          )}

          <div className="flex flex-col gap-1">
            <span
              className="inline-flex w-fit items-center gap-1.5 rounded-full border border-slate-700 px-2 py-0.5 text-xs"
              style={{ color: categoryColor(selected.category) }}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: categoryColor(selected.category) }}
              />
              {categoryLabel(selected.category)}
            </span>
            <h4 className="text-base font-medium text-slate-100">{selected.title}</h4>
            <span className="text-xs text-slate-500">
              {dateTimeFormatter.format(new Date(selected.published_at))}
            </span>
          </div>

          {selected.summary && <p className="text-sm text-slate-300">{selected.summary}</p>}

          <a
            href={selected.source_url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-xs text-sky-400 hover:underline"
          >
            Source: {selected.source_name} ↗
          </a>
          <span className="text-[10px] text-slate-600">
            Verification status: {selected.verification_status}
          </span>

          <div className="mt-2 flex flex-col gap-2 border-t border-slate-800 pt-3">
            <h5 className="text-sm font-medium text-slate-200">Post-event price performance</h5>
            <p className="text-xs text-slate-500">
              Historical observation only — not a recommendation, and not a claim that this event
              caused the price movement.
            </p>

            {isLoading && <p className="text-sm text-slate-500">Loading…</p>}
            {errorMessage && <p className="text-sm text-rose-400">{errorMessage}</p>}

            {impact && (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[480px] text-xs">
                    <thead className="text-left text-slate-500">
                      <tr>
                        <th className="py-1 pr-2 font-medium">Window</th>
                        <th className="py-1 pr-2 text-right font-medium">Stock</th>
                        <th className="py-1 pr-2 text-right font-medium">NIFTY 50</th>
                        <th className="py-1 pr-2 text-right font-medium">Relative</th>
                        <th className="py-1 pr-2 text-right font-medium">Max rise</th>
                        <th className="py-1 text-right font-medium">Max drawdown</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {impact.windows.map((w) => (
                        <tr key={w.trading_days}>
                          <td className="py-1.5 pr-2 text-slate-300">{WINDOW_LABELS[w.trading_days]}</td>
                          {w.status === 'ok' ? (
                            <>
                              <td className={`py-1.5 pr-2 text-right tabular-nums ${toneClass(w.stock_return_pct)}`}>
                                {formatPercent(w.stock_return_pct)}
                              </td>
                              <td className={`py-1.5 pr-2 text-right tabular-nums ${toneClass(w.benchmark_return_pct)}`}>
                                {formatPercent(w.benchmark_return_pct)}
                              </td>
                              <td className={`py-1.5 pr-2 text-right tabular-nums ${toneClass(w.relative_return_pct)}`}>
                                {formatPercent(w.relative_return_pct)}
                              </td>
                              <td className="py-1.5 pr-2 text-right tabular-nums text-emerald-400">
                                {formatPercent(w.max_rise_pct)}
                              </td>
                              <td className="py-1.5 text-right tabular-nums text-rose-400">
                                {formatPercent(w.max_drawdown_pct)}
                              </td>
                            </>
                          ) : (
                            <td colSpan={5} className="py-1.5 text-right text-slate-500 italic">
                              {w.status === 'pending' ? 'Not enough time has passed yet' : 'Data unavailable'}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!impact.benchmark_available && (
                  <p className="text-xs text-amber-400">
                    NIFTY 50 benchmark data isn&apos;t available for this period, so relative
                    returns couldn&apos;t be computed.
                  </p>
                )}

                {impact.interpretation.length > 0 && (
                  <ul className="flex flex-col gap-1 rounded-md bg-slate-950/60 p-3 text-sm text-slate-300">
                    {impact.interpretation.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
