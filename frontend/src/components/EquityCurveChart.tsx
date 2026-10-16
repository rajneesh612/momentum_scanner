import { useEffect, useMemo, useRef, useState } from 'react'

import type { BacktestEquityPoint, BacktestTrade, StockEvent } from '../types'
import { clamp, niceScale } from '../utils/chartScale'
import { categoryColor } from '../utils/eventCategories'
import { clampIndex, useZoomPan } from '../utils/useZoomPan'
import ChartRangeControls from './ChartRangeControls'

interface EquityCurveChartProps {
  equityCurve: BacktestEquityPoint[]
  trades: BacktestTrade[]
  initialCapital: number
  events?: StockEvent[]
  onEventMarkerClick?: (events: StockEvent[]) => void
}

const VIEWBOX_WIDTH = 720
const MARGIN = { top: 12, right: 72, bottom: 28, left: 72 }
const EVENTS_ROW_HEIGHT = 26
const HEIGHT = 260 + EVENTS_ROW_HEIGHT

const STRATEGY_COLOR = '#3b82f6' // series slot 1 - blue
const BENCHMARK_COLOR = '#eb6834' // series slot 2 - orange
const GRIDLINE = '#1e293b'
const MUTED = '#64748b'
const CROSSHAIR = '#94a3b8'
const ENTRY_COLOR = '#34d399'
const EXIT_COLOR = '#fb7185'

const currencyFormatter = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })
const dateFormatter = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' })
const fullDateFormatter = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

function formatCurrency(value: number): string {
  return `₹${currencyFormatter.format(value)}`
}

function formatSignedCurrency(value: number): string {
  return `${value >= 0 ? '+' : '-'}₹${currencyFormatter.format(Math.abs(value))}`
}

export default function EquityCurveChart({
  equityCurve,
  trades,
  initialCapital,
  events = [],
  onEventMarkerClick,
}: EquityCurveChartProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const zoom = useZoomPan({
    length: equityCurve.length,
    firstDate: equityCurve[0]?.date,
    lastDate: equityCurve[equityCurve.length - 1]?.date,
  })

  // See PriceSmaChart.tsx for why this is necessary: a hover index from
  // before a zoom/pan can point past the end of the now-smaller visible
  // slice, which otherwise crashes the render (the blank-chart bug).
  useEffect(() => {
    setHoverIndex(null)
  }, [zoom.range.start, zoom.range.end])

  const benchmarkFull = useMemo(() => {
    if (equityCurve.length === 0) return []
    const baseClose = equityCurve[0].close
    return equityCurve.map((p) => (baseClose > 0 ? (p.close / baseClose) * initialCapital : initialCapital))
  }, [equityCurve, initialCapital])

  const header = (
    <div className="flex flex-col gap-1">
      <h2 className="text-sm font-medium text-slate-200">Investment Growth Over Time</h2>
      <p className="text-xs text-slate-500">
        Shows what your ₹{currencyFormatter.format(initialCapital)} would have been worth, day by
        day, following the SMA strategy versus simply buying and holding — both starting from the
        same amount on the same date.
      </p>
    </div>
  )

  if (equityCurve.length < 2) {
    return (
      <div className="flex flex-col gap-3">
        {header}
        <div className="flex min-h-[120px] items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
          Not enough data to draw a chart for this run.
        </div>
      </div>
    )
  }

  const visible = zoom.range.end >= zoom.range.start ? equityCurve.slice(zoom.range.start, zoom.range.end + 1) : []
  const benchmark = zoom.range.end >= zoom.range.start ? benchmarkFull.slice(zoom.range.start, zoom.range.end + 1) : []

  if (visible.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        {header}
        <div className="flex min-h-[120px] flex-col items-center justify-center gap-2 rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
          No data in the current zoom range.
          <button
            type="button"
            onClick={zoom.reset}
            className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-slate-500"
          >
            Reset zoom
          </button>
        </div>
      </div>
    )
  }

  const safeHoverIndex = clampIndex(hoverIndex, visible.length)

  const plotTop = MARGIN.top
  const plotBottom = HEIGHT - MARGIN.bottom
  const plotHeight = plotBottom - plotTop
  const plotLeft = MARGIN.left
  const plotRight = VIEWBOX_WIDTH - MARGIN.right
  const plotWidth = plotRight - plotLeft

  const allValues = [...visible.map((p) => p.equity), ...benchmark]
  const { min, max, ticks } = niceScale(Math.min(...allValues), Math.max(...allValues))

  const xAt = (i: number) => plotLeft + (visible.length <= 1 ? 0 : (i / (visible.length - 1)) * plotWidth)
  const yAt = (value: number) => plotBottom - ((value - min) / (max - min)) * plotHeight

  const strategyPath = visible.map((p, i) => `${i === 0 ? 'M' : 'L'}${xAt(i)},${yAt(p.equity)}`).join(' ')
  const benchmarkPath = benchmark.map((v, i) => `${i === 0 ? 'M' : 'L'}${xAt(i)},${yAt(v)}`).join(' ')

  const tickTarget = 6
  const tickStep = Math.max(1, Math.ceil(visible.length / tickTarget))
  const xTickIndices = visible.map((_, i) => i).filter((i) => i % tickStep === 0 || i === visible.length - 1)

  const dateIndex = new Map(visible.map((p, i) => [p.date, i]))

  // Group strictly by the event's own real date — never by rounded pixel
  // proximity, which would merge distinct dates into one marker at a
  // synthetic position belonging to neither (see PriceSmaChart.tsx).
  const chartStart = visible[0].date
  const chartEnd = visible[visible.length - 1].date
  const eventsRowY = plotBottom + EVENTS_ROW_HEIGHT
  const eventClusters = (() => {
    const buckets = new Map<string, StockEvent[]>()
    for (const event of events) {
      const eventDate = event.published_at.slice(0, 10)
      if (eventDate < chartStart || eventDate > chartEnd) continue
      const bucket = buckets.get(eventDate) ?? []
      bucket.push(event)
      buckets.set(eventDate, bucket)
    }

    return [...buckets.entries()].map(([eventDate, bucketEvents]) => {
      let nearestIndex = 0
      for (let i = 0; i < visible.length; i++) {
        nearestIndex = i
        if (visible[i].date >= eventDate) break
      }
      return { date: eventDate, x: xAt(nearestIndex), events: bucketEvents }
    })
  })()

  function pixelsPerIndex(): number {
    const svg = svgRef.current
    if (!svg) return 0
    const rect = svg.getBoundingClientRect()
    const screenPxPerUserUnit = rect.width / VIEWBOX_WIDTH
    const userUnitsPerIndex = visible.length <= 1 ? plotWidth : plotWidth / (visible.length - 1)
    return screenPxPerUserUnit * userUnitsPerIndex
  }

  function handlePointerMove(e: React.PointerEvent<SVGRectElement>) {
    if (e.buttons === 1 && zoom.isPanning) {
      zoom.updatePan(e.clientX, pixelsPerIndex())
      return
    }
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const userX = ((e.clientX - rect.left) / rect.width) * VIEWBOX_WIDTH
    const t = clamp((userX - plotLeft) / plotWidth, 0, 1)
    setHoverIndex(Math.round(t * (visible.length - 1)))
  }

  function handlePointerDown(e: React.PointerEvent<SVGRectElement>) {
    zoom.startPan(e.clientX)
    handlePointerMove(e)
  }

  function handleWheel(e: React.WheelEvent<SVGSVGElement>) {
    e.preventDefault()
    const svg = svgRef.current
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const userX = ((e.clientX - rect.left) / rect.width) * VIEWBOX_WIDTH
    const t = clamp((userX - plotLeft) / plotWidth, 0, 1)
    const localCenter = Math.round(t * (visible.length - 1))
    zoom.zoomAt(zoom.range.start + localCenter, e.deltaY > 0 ? 1.2 : 0.8)
  }

  const lastIndex = visible.length - 1
  const finalStrategy = visible[lastIndex].equity
  const finalBenchmark = benchmark[lastIndex]
  const readoutIndex = safeHoverIndex ?? lastIndex
  const readoutDate = visible[readoutIndex].date
  const readoutStrategy = visible[readoutIndex].equity
  const readoutBenchmark = benchmark[readoutIndex]

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        {header}
        <ChartRangeControls
          firstDate={equityCurve[0].date}
          lastDate={equityCurve[equityCurve.length - 1].date}
          onSelectPreset={(days) => zoom.setPresetDays(days, (i) => equityCurve[i].date)}
          onReset={zoom.reset}
          isZoomed={zoom.isZoomed}
        />
      </div>

      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
        <div className="flex flex-col gap-0.5">
          <span className="text-slate-500">
            {safeHoverIndex === null ? 'At end date' : 'On hover'} — {fullDateFormatter.format(new Date(readoutDate))}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded-full" style={{ backgroundColor: STRATEGY_COLOR }} />
            <span className="text-slate-300">SMA Strategy</span>
            <span className="font-mono tabular-nums text-slate-100">{formatCurrency(readoutStrategy)}</span>
            <span className="font-mono tabular-nums text-slate-500">
              ({formatSignedCurrency(readoutStrategy - initialCapital)})
            </span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-3 rounded-full" style={{ backgroundColor: BENCHMARK_COLOR }} />
            <span className="text-slate-300">Buy &amp; Hold</span>
            <span className="font-mono tabular-nums text-slate-100">{formatCurrency(readoutBenchmark)}</span>
            <span className="font-mono tabular-nums text-slate-500">
              ({formatSignedCurrency(readoutBenchmark - initialCapital)})
            </span>
          </span>
        </div>
        <div className="flex flex-col items-end gap-0.5 text-slate-500">
          <span>Start: {formatCurrency(initialCapital)}</span>
          <span>End (SMA Strategy): {formatCurrency(finalStrategy)}</span>
          <span>End (Buy &amp; Hold): {formatCurrency(finalBenchmark)}</span>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEWBOX_WIDTH} ${HEIGHT}`}
        className="w-full touch-none"
        style={{ height: 'auto' }}
        role="img"
        aria-label={`Investment growth chart. Starting capital ${formatCurrency(initialCapital)} on ${fullDateFormatter.format(
          new Date(visible[0].date),
        )}. SMA Strategy ended at ${formatCurrency(finalStrategy)}; Buy and Hold ended at ${formatCurrency(
          finalBenchmark,
        )}, on ${fullDateFormatter.format(new Date(visible[lastIndex].date))}. Scroll to zoom, drag to pan.`}
        onWheel={handleWheel}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={plotLeft} x2={plotRight} y1={yAt(tick)} y2={yAt(tick)} stroke={GRIDLINE} strokeWidth={1} />
            <text x={plotLeft - 8} y={yAt(tick)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={MUTED}>
              {formatCurrency(tick)}
            </text>
          </g>
        ))}

        <path d={benchmarkPath} fill="none" stroke={BENCHMARK_COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" opacity={0.85} />
        <path d={strategyPath} fill="none" stroke={STRATEGY_COLOR} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {trades.map((t) => {
          const entryIdx = dateIndex.get(t.entry_date)
          if (entryIdx === undefined) return null
          const entryY = yAt(visible[entryIdx].equity)
          return (
            <polygon
              key={`entry-${t.entry_date}`}
              points={`${xAt(entryIdx)},${entryY - 7} ${xAt(entryIdx) - 5},${entryY + 2} ${xAt(entryIdx) + 5},${entryY + 2}`}
              fill={ENTRY_COLOR}
              stroke="#0f172a"
              strokeWidth={1}
            />
          )
        })}
        {trades
          .filter((t) => !t.is_open)
          .map((t) => {
            const exitIdx = dateIndex.get(t.exit_date)
            if (exitIdx === undefined) return null
            const exitY = yAt(visible[exitIdx].equity)
            return (
              <polygon
                key={`exit-${t.exit_date}`}
                points={`${xAt(exitIdx)},${exitY + 7} ${xAt(exitIdx) - 5},${exitY - 2} ${xAt(exitIdx) + 5},${exitY - 2}`}
                fill={EXIT_COLOR}
                stroke="#0f172a"
                strokeWidth={1}
              />
            )
          })}

        {/* End-of-line markers + direct value labels for both series */}
        <circle cx={xAt(lastIndex)} cy={yAt(finalStrategy)} r={4} fill={STRATEGY_COLOR} stroke="#0f172a" strokeWidth={2} />
        <text x={xAt(lastIndex) + 9} y={yAt(finalStrategy)} dominantBaseline="middle" fontSize={11} fill={STRATEGY_COLOR}>
          {formatCurrency(finalStrategy)}
        </text>
        <circle cx={xAt(lastIndex)} cy={yAt(finalBenchmark)} r={4} fill={BENCHMARK_COLOR} stroke="#0f172a" strokeWidth={2} />
        <text x={xAt(lastIndex) + 9} y={yAt(finalBenchmark)} dominantBaseline="middle" fontSize={11} fill={BENCHMARK_COLOR}>
          {formatCurrency(finalBenchmark)}
        </text>

        {xTickIndices.map((i) => (
          <text key={i} x={xAt(i)} y={plotBottom + 16} textAnchor="middle" fontSize={10} fill={MUTED}>
            {dateFormatter.format(new Date(visible[i].date))}
          </text>
        ))}

        {eventClusters.length > 0 && (
          <text x={plotLeft - 8} y={eventsRowY} textAnchor="end" dominantBaseline="middle" fontSize={9} fill={MUTED}>
            Events
          </text>
        )}
        {eventClusters.map((cluster) => {
          const primaryColor = categoryColor(cluster.events[0].category)
          const label =
            cluster.events.length === 1
              ? cluster.events[0].title
              : `${cluster.events.length} events on ${cluster.date}`
          return (
            <g
              key={`events-${cluster.date}`}
              className="cursor-pointer"
              onClick={() => onEventMarkerClick?.(cluster.events)}
              role="button"
              aria-label={label}
            >
              <circle cx={cluster.x} cy={eventsRowY} r={9} fill="transparent" />
              <circle cx={cluster.x} cy={eventsRowY} r={5} fill={primaryColor} stroke="#0f172a" strokeWidth={1.5} />
              {cluster.events.length > 1 && (
                <text
                  x={cluster.x}
                  y={eventsRowY}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fontSize={7}
                  fontWeight={700}
                  fill="#0f172a"
                >
                  {cluster.events.length}
                </text>
              )}
            </g>
          )
        })}

        {safeHoverIndex !== null && (
          <>
            <line x1={xAt(safeHoverIndex)} x2={xAt(safeHoverIndex)} y1={plotTop} y2={plotBottom} stroke={CROSSHAIR} strokeWidth={1} />
            <circle cx={xAt(safeHoverIndex)} cy={yAt(visible[safeHoverIndex].equity)} r={4} fill={STRATEGY_COLOR} stroke="#0f172a" strokeWidth={2} />
            <circle cx={xAt(safeHoverIndex)} cy={yAt(benchmark[safeHoverIndex])} r={4} fill={BENCHMARK_COLOR} stroke="#0f172a" strokeWidth={2} />
          </>
        )}

        <rect
          x={plotLeft}
          y={plotTop}
          width={plotWidth}
          height={plotHeight}
          fill="transparent"
          onPointerMove={handlePointerMove}
          onPointerDown={handlePointerDown}
          onPointerUp={zoom.endPan}
          onPointerLeave={() => {
            zoom.endPan()
            setHoverIndex(null)
          }}
          style={{ cursor: zoom.isPanning ? 'grabbing' : 'grab' }}
        />
      </svg>
    </div>
  )
}
