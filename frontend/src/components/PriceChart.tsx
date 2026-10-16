import { useRef, useState } from 'react'

import type { PriceHistoryPoint } from '../types'
import { clamp, niceScale } from '../utils/chartScale'

interface PriceChartProps {
  symbol: string
  prices: PriceHistoryPoint[]
}

const VIEWBOX_WIDTH = 720
const MARGIN = { top: 8, right: 12, bottom: 28, left: 52 }
const PRICE_HEIGHT = 200
const VOLUME_HEIGHT = 64
const PANEL_GAP = 10

const ACCENT = '#3b82f6'
const ACCENT_FILL = 'rgba(59, 130, 246, 0.1)'
const GRIDLINE = '#1e293b'
const BASELINE = '#334155'
const MUTED = '#64748b'
const VOLUME_BAR = '#475569'
const VOLUME_BAR_HOVER = '#64748b'
const CROSSHAIR = '#94a3b8'

const priceFormatter = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const volumeFormatter = new Intl.NumberFormat('en-IN')
const dateFormatter = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' })
const fullDateFormatter = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

export default function PriceChart({ symbol, prices }: PriceChartProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  if (prices.length < 2) {
    return (
      <p className="text-sm text-slate-500">Not enough data points to draw a chart yet.</p>
    )
  }

  const priceTop = MARGIN.top
  const priceBottom = MARGIN.top + PRICE_HEIGHT
  const volumeTop = priceBottom + PANEL_GAP
  const volumeBottom = volumeTop + VOLUME_HEIGHT
  const plotLeft = MARGIN.left
  const plotRight = VIEWBOX_WIDTH - MARGIN.right
  const plotWidth = plotRight - plotLeft
  const totalHeight = volumeBottom + MARGIN.bottom

  const closes = prices.map((p) => p.close)
  const { min: priceMin, max: priceMax, ticks: priceTicks } = niceScale(
    Math.min(...closes),
    Math.max(...closes),
  )
  const maxVolume = Math.max(...prices.map((p) => p.volume), 1)

  const xAt = (i: number) => plotLeft + (i / (prices.length - 1)) * plotWidth
  const priceYAt = (close: number) =>
    priceBottom - ((close - priceMin) / (priceMax - priceMin)) * PRICE_HEIGHT
  const volumeYAt = (volume: number) => volumeBottom - (volume / maxVolume) * VOLUME_HEIGHT

  const linePath = prices.map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(i)},${priceYAt(p.close)}`).join(' ')
  const areaPath = `${linePath} L${xAt(prices.length - 1)},${priceBottom} L${xAt(0)},${priceBottom} Z`

  const barWidth = Math.max(1.5, Math.min(24, (plotWidth / prices.length) * 0.6))

  const tickTarget = 6
  const tickStep = Math.max(1, Math.ceil(prices.length / tickTarget))
  const xTickIndices = prices
    .map((_, i) => i)
    .filter((i) => i % tickStep === 0 || i === prices.length - 1)

  const last = prices[prices.length - 1]
  const displayed = prices[hoverIndex ?? prices.length - 1]
  const closeColor = displayed.close >= displayed.open ? 'text-emerald-400' : 'text-rose-400'

  function handlePointer(e: React.PointerEvent<SVGRectElement>) {
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const userX = ((e.clientX - rect.left) / rect.width) * VIEWBOX_WIDTH
    const t = clamp((userX - plotLeft) / plotWidth, 0, 1)
    setHoverIndex(Math.round(t * (prices.length - 1)))
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-medium text-slate-200">Price</h3>
        <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs tabular-nums text-slate-400">
          <span className="text-slate-500">{fullDateFormatter.format(new Date(displayed.date))}</span>
          <span>
            O <span className="text-slate-200">{priceFormatter.format(displayed.open)}</span>
          </span>
          <span>
            H <span className="text-slate-200">{priceFormatter.format(displayed.high)}</span>
          </span>
          <span>
            L <span className="text-slate-200">{priceFormatter.format(displayed.low)}</span>
          </span>
          <span>
            C <span className={closeColor}>{priceFormatter.format(displayed.close)}</span>
          </span>
          <span>
            Vol <span className="text-slate-200">{volumeFormatter.format(displayed.volume)}</span>
          </span>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${totalHeight}`}
        className="w-full"
        style={{ height: 'auto' }}
        role="img"
        aria-label={`Close price and volume chart for ${symbol}, ${fullDateFormatter.format(
          new Date(prices[0].date),
        )} to ${fullDateFormatter.format(new Date(last.date))}`}
      >
        {priceTicks.map((tick) => (
          <g key={tick}>
            <line x1={plotLeft} x2={plotRight} y1={priceYAt(tick)} y2={priceYAt(tick)} stroke={GRIDLINE} strokeWidth={1} />
            <text x={plotLeft - 8} y={priceYAt(tick)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={MUTED}>
              {tick.toFixed(0)}
            </text>
          </g>
        ))}

        <path d={areaPath} fill={ACCENT_FILL} stroke="none" />
        <path d={linePath} fill="none" stroke={ACCENT} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        <circle cx={xAt(prices.length - 1)} cy={priceYAt(last.close)} r={4} fill={ACCENT} stroke="#0f172a" strokeWidth={2} />
        <text x={xAt(prices.length - 1) - 8} y={priceYAt(last.close) - 8} textAnchor="end" fontSize={11} fill="#e2e8f0">
          {priceFormatter.format(last.close)}
        </text>

        <text x={plotLeft - 8} y={volumeTop + 4} textAnchor="end" fontSize={9} fill={MUTED}>
          {volumeFormatter.format(maxVolume)}
        </text>
        {prices.map((p, i) => (
          <rect
            key={p.date}
            x={xAt(i) - barWidth / 2}
            y={volumeYAt(p.volume)}
            width={barWidth}
            height={Math.max(0, volumeBottom - volumeYAt(p.volume))}
            rx={1.5}
            fill={i === hoverIndex ? VOLUME_BAR_HOVER : VOLUME_BAR}
          />
        ))}
        <line x1={plotLeft} x2={plotRight} y1={volumeBottom} y2={volumeBottom} stroke={BASELINE} strokeWidth={1} />

        {xTickIndices.map((i) => (
          <text key={i} x={xAt(i)} y={volumeBottom + 16} textAnchor="middle" fontSize={10} fill={MUTED}>
            {dateFormatter.format(new Date(prices[i].date))}
          </text>
        ))}

        {hoverIndex !== null && (
          <>
            <line
              x1={xAt(hoverIndex)}
              x2={xAt(hoverIndex)}
              y1={priceTop}
              y2={volumeBottom}
              stroke={CROSSHAIR}
              strokeWidth={1}
            />
            <circle
              cx={xAt(hoverIndex)}
              cy={priceYAt(prices[hoverIndex].close)}
              r={4}
              fill={ACCENT}
              stroke="#0f172a"
              strokeWidth={2}
            />
          </>
        )}

        <rect
          x={plotLeft}
          y={priceTop}
          width={plotWidth}
          height={volumeBottom - priceTop}
          fill="transparent"
          onPointerMove={handlePointer}
          onPointerDown={handlePointer}
          onPointerLeave={() => setHoverIndex(null)}
          style={{ cursor: 'crosshair' }}
        />
      </svg>
    </div>
  )
}
