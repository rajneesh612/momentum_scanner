import type { PriceHistoryPoint } from '../types'

interface PriceHistoryTableProps {
  prices: PriceHistoryPoint[]
}

const priceFormatter = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const volumeFormatter = new Intl.NumberFormat('en-IN')

export default function PriceHistoryTable({ prices }: PriceHistoryTableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="bg-slate-900 text-left text-xs tracking-wide text-slate-400 uppercase">
          <tr>
            <th className="px-4 py-2 font-medium">Date</th>
            <th className="px-4 py-2 text-right font-medium">Open</th>
            <th className="px-4 py-2 text-right font-medium">High</th>
            <th className="px-4 py-2 text-right font-medium">Low</th>
            <th className="px-4 py-2 text-right font-medium">Close</th>
            <th className="px-4 py-2 text-right font-medium">Adj Close</th>
            <th className="px-4 py-2 text-right font-medium">Volume</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800">
          {prices.map((price) => (
            <tr key={price.date} className="hover:bg-slate-900/50">
              <td className="px-4 py-2 font-mono text-slate-300">{price.date}</td>
              <td className="px-4 py-2 text-right tabular-nums">{priceFormatter.format(price.open)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{priceFormatter.format(price.high)}</td>
              <td className="px-4 py-2 text-right tabular-nums">{priceFormatter.format(price.low)}</td>
              <td className="px-4 py-2 text-right font-medium tabular-nums text-slate-100">
                {priceFormatter.format(price.close)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-400">
                {priceFormatter.format(price.adjusted_close)}
              </td>
              <td className="px-4 py-2 text-right tabular-nums text-slate-400">
                {volumeFormatter.format(price.volume)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
