import type { BacktestEquityPoint, BacktestTrade } from '../types'

interface TradesTableProps {
  trades: BacktestTrade[]
  equityCurve: BacktestEquityPoint[]
}

const priceFormatter = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const currencyFormatter = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

function formatSignedCurrency(value: number): string {
  return `${value >= 0 ? '+' : '-'}₹${currencyFormatter.format(Math.abs(value))}`
}

export default function TradesTable({ trades, equityCurve }: TradesTableProps) {
  if (trades.length === 0) {
    return <p className="text-sm text-slate-500">No trades were triggered in this window.</p>
  }

  // The amount actually invested at entry equals the portfolio's equity
  // value on the entry date (buying all-in at that day's close leaves
  // equity unchanged in the moment) — so the absolute ₹ P&L for a trade
  // is derivable from equity_curve + return_pct, not invented.
  const equityByDate = new Map(equityCurve.map((p) => [p.date, p.equity]))

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="bg-slate-900 text-left text-xs tracking-wide text-slate-400 uppercase">
          <tr>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Entry</th>
            <th className="px-4 py-2 text-right font-medium">Entry price</th>
            <th className="px-4 py-2 font-medium">Exit</th>
            <th className="px-4 py-2 text-right font-medium">Exit price</th>
            <th className="px-4 py-2 text-right font-medium">P&amp;L (₹)</th>
            <th className="px-4 py-2 text-right font-medium">Return</th>
            <th className="px-4 py-2 text-right font-medium">Days held</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {trades.map((trade) => {
            const entryEquity = equityByDate.get(trade.entry_date)
            const absolutePl = entryEquity !== undefined ? entryEquity * (trade.return_pct / 100) : null
            const toneClass = trade.return_pct >= 0 ? 'text-emerald-400' : 'text-rose-400'

            return (
              <tr key={trade.entry_date} className="hover:bg-slate-900/50">
                <td className="px-4 py-2">
                  <span
                    className={`rounded-full border px-1.5 py-0.5 text-[10px] uppercase ${
                      trade.is_open
                        ? 'border-amber-700/60 bg-amber-900/30 text-amber-400'
                        : 'border-slate-700 bg-slate-800/60 text-slate-400'
                    }`}
                  >
                    {trade.is_open ? 'Open' : 'Closed'}
                  </span>
                </td>
                <td className="px-4 py-2 font-mono text-slate-300">{trade.entry_date}</td>
                <td className="px-4 py-2 text-right tabular-nums">{priceFormatter.format(trade.entry_price)}</td>
                <td className="px-4 py-2 font-mono text-slate-300">
                  {trade.is_open ? 'Marked to latest close' : trade.exit_date}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">{priceFormatter.format(trade.exit_price)}</td>
                <td className={`px-4 py-2 text-right tabular-nums ${toneClass}`}>
                  {absolutePl !== null ? formatSignedCurrency(absolutePl) : '—'}
                  {trade.is_open && <span className="ml-1 text-[10px] text-slate-500">(unrealized)</span>}
                </td>
                <td className={`px-4 py-2 text-right font-medium tabular-nums ${toneClass}`}>
                  {trade.return_pct >= 0 ? '+' : ''}
                  {trade.return_pct.toFixed(2)}%
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-slate-400">{trade.holding_days}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="border-t border-slate-800 px-4 py-2 text-xs text-slate-500">
        Open positions show an <span className="text-amber-400">unrealized</span> P&amp;L marked to
        the last available close — not yet a completed (realized) trade.
      </p>
    </div>
  )
}
