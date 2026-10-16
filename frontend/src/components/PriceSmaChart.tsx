import { useEffect, useRef, useState } from 'react'

import type { BacktestEquityPoint, BacktestTrade, StockEvent } from '../types'
import { clamp, niceScale } from '../utils/chartScale'
import { categoryColor, categoryLabel } from '../utils/eventCategories'
import { clampIndex, isValidIndex, useZoomPan } from '../utils/useZoomPan'
import ChartRangeControls from './ChartRangeControls'

interface PriceSmaChartProps {
  equityCurve: BacktestEquityPoint[]
  trades: BacktestTrade[]
  shortWindow: number
  longWindow: number
  barLabel: string
  events?: StockEvent[]
  onEventMarkerClick?: (events: StockEvent[]) => void
}

const VIEWBOX_WIDTH = 720
const MARGIN = { top: 12, right: 12, bottom: 28, left: 64 }
const TRADES_ROW_HEIGHT = 30
const PLOT_HEIGHT = 220
const HEIGHT = PLOT_HEIGHT + MARGIN.top + MARGIN.bottom + TRADES_ROW_HEIGHT
const MARKER_LAYER_PX = 9
const EVENT_LAYER_PX = 8

const CLOSE_COLOR = '#cbd5e1'
const SHORT_SMA_COLOR = '#3b82f6'
const LONG_SMA_COLOR = '#eb6834'
const GRIDLINE = '#1e293b'
const MUTED = '#64748b'
const CROSSHAIR = '#94a3b8'
const BUY_COLOR = '#34d399'
const SELL_COLOR = '#fb7185'
const OPEN_COLOR = '#fbbf24'

const priceFormatter = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const dateFormatter = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' })
const fullDateFormatter = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

function fmt(value: number | null): string {
  return value === null ? '—' : priceFormatter.format(value)
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

type TradeMarkerType = 'buy' | 'sell' | 'open'

interface TradeMarker {
  type: TradeMarkerType
  date: string
  trade: BacktestTrade
}

interface EventPositionCluster {
  idx: number
  x: number
  y: number
  dateGroups: { date: string; items: StockEvent[] }[]
}

export default function PriceSmaChart({
  equityCurve,
  trades,
  shortWindow,
  longWindow,
  barLabel,
  events = [],
  onEventMarkerClick,
}: PriceSmaChartProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [hoveredEvents, setHoveredEvents] = useState<EventPositionCluster | null>(null)
  const zoom = useZoomPan({
    length: equityCurve.length,
    firstDate: equityCurve[0]?.date,
    lastDate: equityCurve[equityCurve.length - 1]?.date,
  })

  // A stale hover index from before a zoom/pan (pointing past the end of
  // the now-smaller visible slice) must never survive into a render that
  // indexes `visible[hoverIndex]` — this was the root cause of an earlier
  // blank-chart-after-zoom bug. Clearing it here, plus clamping at every
  // use site below, are both belt-and-suspenders against that class of
  // bug.
  useEffect(() => {
    setHoverIndex(null)
    setHoveredEvents(null)
  }, [zoom.range.start, zoom.range.end])

  if (equityCurve.length < 2) {
    return (
      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-slate-200">Stock Price &amp; SMA Signals</h2>
        <div className="flex min-h-[120px] items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-500">
          Not enough data to draw a chart for this run.
        </div>
      </div>
    )
  }

  const visible = zoom.range.end >= zoom.range.start ? equityCurve.slice(zoom.range.start, zoom.range.end + 1) : []

  if (visible.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-slate-200">Stock Price &amp; SMA Signals</h2>
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
  // `hoveredEvents.idx` was captured as a local index into a *previous*
  // render's `visible` slice. A zoom/pan re-slices `visible` to a
  // different length on every change, and the effect that clears
  // `hoveredEvents` on range change only runs after this render commits
  // — so this render can still see a stale `hoveredEvents` whose `idx`
  // is now out of bounds for the *current* `visible`. Re-validating here
  // (rather than trusting the effect alone) is what prevents
  // `visible[hoveredEvents.idx]` from evaluating to `undefined` and
  // crashing the render — this was the root cause of the white-screen
  // bug when zooming while a news-event tooltip was open.
  const hoveredEventsValid = hoveredEvents !== null && isValidIndex(hoveredEvents.idx, visible.length)

  const plotTop = MARGIN.top
  const plotBottom = plotTop + PLOT_HEIGHT
  const plotLeft = MARGIN.left
  const plotRight = VIEWBOX_WIDTH - MARGIN.right
  const plotWidth = plotRight - plotLeft
  const tradesRowY = plotBottom + TRADES_ROW_HEIGHT

  const allValues = visible.flatMap((p) => [p.close, p.short_sma, p.long_sma].filter((v): v is number => v !== null))
  const { min, max, ticks } = niceScale(Math.min(...allValues), Math.max(...allValues))

  const xAt = (i: number) => plotLeft + (visible.length <= 1 ? 0 : (i / (visible.length - 1)) * plotWidth)
  const yAt = (value: number) => plotBottom - ((value - min) / (max - min)) * PLOT_HEIGHT

  function linePath(key: 'close' | 'short_sma' | 'long_sma'): string {
    let path = ''
    let drawing = false
    visible.forEach((p, i) => {
      const value = p[key]
      if (value === null) {
        drawing = false
        return
      }
      path += `${drawing ? 'L' : 'M'}${xAt(i)},${yAt(value)} `
      drawing = true
    })
    return path.trim()
  }

  const dateIndex = new Map(visible.map((p, i) => [p.date, i]))

  const tickTarget = 6
  const tickStep = Math.max(1, Math.ceil(visible.length / tickTarget))
  const xTickIndices = visible.map((_, i) => i).filter((i) => i % tickStep === 0 || i === visible.length - 1)

  const chartStart = visible[0].date
  const chartEnd = visible[visible.length - 1].date

  // The announcement date snaps to the first trading session on/after it
  // (handles non-trading-day announcements) — never backward, never to a
  // day the stock didn't actually trade.
  function nearestVisibleIndex(dateStr: string): number {
    let nearest = 0
    for (let i = 0; i < visible.length; i++) {
      nearest = i
      if (visible[i].date >= dateStr) break
    }
    return nearest
  }

  // Trade markers (unchanged from before this change): group strictly by
  // the item's own real date — never by rounded pixel proximity, which
  // would merge distinct dates into one marker at a position that
  // belongs to neither of them.
  function clusterByDate<T>(items: T[], getDate: (item: T) => string) {
    const buckets = new Map<string, T[]>()
    for (const item of items) {
      const date = getDate(item)
      if (date < chartStart || date > chartEnd) continue
      const bucket = buckets.get(date) ?? []
      bucket.push(item)
      buckets.set(date, bucket)
    }
    return [...buckets.entries()].map(([date, bucketItems]) => ({
      date,
      x: xAt(nearestVisibleIndex(date)),
      items: bucketItems,
    }))
  }

  const tradeMarkers: TradeMarker[] = []
  for (const t of trades) {
    tradeMarkers.push({ type: 'buy', date: t.entry_date, trade: t })
    tradeMarkers.push({ type: t.is_open ? 'open' : 'sell', date: t.exit_date, trade: t })
  }
  const tradeClusters = clusterByDate(tradeMarkers, (m) => m.date)

  // News events render directly on the price line, at the close price of
  // the trading session their announcement date resolves to. Two levels
  // of grouping: first by the event's own real date (for correct counts
  // and tooltip content), then by the *resolved trading-day index* —
  // because two different dates (e.g. a Saturday and Sunday filing) can
  // both snap to the same next trading session and would otherwise sit
  // exactly on top of each other. Grouping/offsetting is display-only;
  // no event date or price is ever changed.
  const eventPositionGroups: EventPositionCluster[] = (() => {
    const byDate = new Map<string, StockEvent[]>()
    for (const event of events) {
      const date = event.published_at.slice(0, 10)
      if (date < chartStart || date > chartEnd) continue
      const bucket = byDate.get(date) ?? []
      bucket.push(event)
      byDate.set(date, bucket)
    }

    const byIndex = new Map<number, { date: string; items: StockEvent[] }[]>()
    for (const [date, items] of byDate) {
      const idx = nearestVisibleIndex(date)
      const group = byIndex.get(idx) ?? []
      group.push({ date, items })
      byIndex.set(idx, group)
    }

    return [...byIndex.entries()].map(([idx, dateGroups]) => ({
      idx,
      x: xAt(idx),
      y: yAt(visible[idx].close),
      dateGroups,
    }))
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
    const globalCenter = zoom.range.start + localCenter
    zoom.zoomAt(globalCenter, e.deltaY > 0 ? 1.2 : 0.8)
  }

  const readoutIndex = safeHoverIndex ?? visible.length - 1
  const readoutPoint = visible[readoutIndex]
  const tradeOnReadoutDate = trades.find(
    (t) => t.entry_date === readoutPoint.date || (t.exit_date === readoutPoint.date && !t.is_open),
  )
  let signalLabel = 'Warming up'
  if (readoutPoint.short_sma !== null && readoutPoint.long_sma !== null) {
    signalLabel = readoutPoint.short_sma > readoutPoint.long_sma ? 'Bullish (above)' : 'Bearish (below)'
  }

  const allEventItems = hoveredEventsValid ? (hoveredEvents?.dateGroups.flatMap((g) => g.items) ?? []) : []
  const totalHoveredEvents = allEventItems.length
  const tooltipXPct = hoveredEventsValid && hoveredEvents ? (hoveredEvents.x / VIEWBOX_WIDTH) * 100 : 0
  const tooltipYPct = hoveredEventsValid && hoveredEvents ? (hoveredEvents.y / HEIGHT) * 100 : 0
  const flipLeft = tooltipXPct > 60
  const flipDown = tooltipYPct < 30

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-medium text-slate-200">Stock Price &amp; SMA Signals</h2>
          <p className="text-xs text-slate-500">
            Closing price with the {shortWindow}-{barLabel} and {longWindow}-{barLabel} moving
            averages the strategy actually traded on. Buy/sell markers sit in their own row below;
            news events are dots on the price line — hover for a preview, click for details.
          </p>
        </div>
        <ChartRangeControls
          firstDate={equityCurve[0].date}
          lastDate={equityCurve[equityCurve.length - 1].date}
          onSelectPreset={(days) => zoom.setPresetDays(days, (i) => equityCurve[i].date)}
          onReset={zoom.reset}
          isZoomed={zoom.isZoomed}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-slate-500">
            {safeHoverIndex === null ? 'Latest' : 'On hover'} — {fullDateFormatter.format(new Date(readoutPoint.date))}
          </span>
          <span>
            Price <span className="font-mono tabular-nums text-slate-100">₹{fmt(readoutPoint.close)}</span>
          </span>
          <span>
            Short SMA <span className="font-mono tabular-nums" style={{ color: SHORT_SMA_COLOR }}>₹{fmt(readoutPoint.short_sma)}</span>
          </span>
          <span>
            Long SMA <span className="font-mono tabular-nums" style={{ color: LONG_SMA_COLOR }}>₹{fmt(readoutPoint.long_sma)}</span>
          </span>
          <span className="text-slate-400">{signalLabel}</span>
        </div>
        {tradeOnReadoutDate && (
          <span className={tradeOnReadoutDate.entry_date === readoutPoint.date ? 'text-emerald-400' : 'text-rose-400'}>
            {tradeOnReadoutDate.entry_date === readoutPoint.date
              ? `BUY @ ₹${fmt(tradeOnReadoutDate.entry_price)}`
              : `SELL @ ₹${fmt(tradeOnReadoutDate.exit_price)} (${tradeOnReadoutDate.return_pct >= 0 ? '+' : ''}${tradeOnReadoutDate.return_pct.toFixed(2)}%)`}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 rounded-full" style={{ backgroundColor: CLOSE_COLOR }} />
          Close price
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 rounded-full" style={{ backgroundColor: SHORT_SMA_COLOR }} />
          Short SMA ({shortWindow})
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-0.5 w-3 rounded-full" style={{ backgroundColor: LONG_SMA_COLOR }} />
          Long SMA ({longWindow})
        </span>
        <span className="flex items-center gap-1" style={{ color: BUY_COLOR }}>
          ▲ Buy
        </span>
        <span className="flex items-center gap-1" style={{ color: SELL_COLOR }}>
          ▼ Sell
        </span>
        <span className="flex items-center gap-1" style={{ color: OPEN_COLOR }}>
          ◆ Open position
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border border-slate-900" style={{ backgroundColor: '#94a3b8' }} />
          News event (colored by category)
        </span>
      </div>

      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEWBOX_WIDTH} ${HEIGHT}`}
          className="w-full touch-none"
          style={{ height: 'auto' }}
          role="img"
          aria-label={`Stock price with ${shortWindow}-${barLabel} and ${longWindow}-${barLabel} SMA lines, buy/sell markers at the strategy's actual trade dates, and news event dots on their announcement dates. Scroll to zoom, drag to pan.`}
          onWheel={handleWheel}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={plotLeft} x2={plotRight} y1={yAt(tick)} y2={yAt(tick)} stroke={GRIDLINE} strokeWidth={1} />
              <text x={plotLeft - 8} y={yAt(tick)} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={MUTED}>
                {tick.toFixed(0)}
              </text>
            </g>
          ))}

          <path d={linePath('close')} fill="none" stroke={CLOSE_COLOR} strokeWidth={1.5} opacity={0.8} />
          <path d={linePath('short_sma')} fill="none" stroke={SHORT_SMA_COLOR} strokeWidth={2} />
          <path d={linePath('long_sma')} fill="none" stroke={LONG_SMA_COLOR} strokeWidth={2} />

          <line x1={plotLeft} x2={plotRight} y1={plotBottom + 2} y2={plotBottom + 2} stroke={GRIDLINE} strokeWidth={1} />
          <text x={plotLeft - 8} y={tradesRowY} textAnchor="end" dominantBaseline="middle" fontSize={9} fill={MUTED}>
            Trades
          </text>
          {tradeClusters.map((cluster) => (
            <g key={`trades-${cluster.date}`}>
              {cluster.items.map((marker, layer) => {
                const idx = dateIndex.get(marker.date)
                if (idx === undefined) return null
                const y = tradesRowY + layer * MARKER_LAYER_PX
                const color = marker.type === 'buy' ? BUY_COLOR : marker.type === 'sell' ? SELL_COLOR : OPEN_COLOR
                const shared = {
                  className: 'cursor-pointer',
                  onPointerEnter: () => setHoverIndex(idx),
                  role: 'img' as const,
                  'aria-label':
                    marker.type === 'buy'
                      ? `Buy at ₹${fmt(marker.trade.entry_price)} on ${marker.date}`
                      : marker.type === 'sell'
                        ? `Sell at ₹${fmt(marker.trade.exit_price)} on ${marker.date}, ${marker.trade.return_pct.toFixed(2)}% return`
                        : `Open position, marked at ₹${fmt(marker.trade.exit_price)} on ${marker.date}`,
                }
                if (marker.type === 'buy') {
                  return (
                    <polygon
                      key={`${marker.type}-${marker.date}-${layer}`}
                      points={`${cluster.x},${y - 5} ${cluster.x - 5},${y + 4} ${cluster.x + 5},${y + 4}`}
                      fill={color}
                      stroke="#0f172a"
                      strokeWidth={1}
                      {...shared}
                    />
                  )
                }
                if (marker.type === 'sell') {
                  return (
                    <polygon
                      key={`${marker.type}-${marker.date}-${layer}`}
                      points={`${cluster.x},${y + 5} ${cluster.x - 5},${y - 4} ${cluster.x + 5},${y - 4}`}
                      fill={color}
                      stroke="#0f172a"
                      strokeWidth={1}
                      {...shared}
                    />
                  )
                }
                return (
                  <polygon
                    key={`${marker.type}-${marker.date}-${layer}`}
                    points={`${cluster.x},${y - 5} ${cluster.x + 5},${y} ${cluster.x},${y + 5} ${cluster.x - 5},${y}`}
                    fill={color}
                    stroke="#0f172a"
                    strokeWidth={1}
                    {...shared}
                  />
                )
              })}
            </g>
          ))}

          {xTickIndices.map((i) => (
            <text key={i} x={xAt(i)} y={plotBottom + 16} textAnchor="middle" fontSize={10} fill={MUTED}>
              {dateFormatter.format(new Date(visible[i].date))}
            </text>
          ))}

          {safeHoverIndex !== null && (
            <line x1={xAt(safeHoverIndex)} x2={xAt(safeHoverIndex)} y1={plotTop} y2={plotBottom} stroke={CROSSHAIR} strokeWidth={1} />
          )}

          {/* Pointer-capture rect for the crosshair/zoom/pan must come
              before the event dots in document order, so the dots (drawn
              after/on top) receive their own hover/click instead of the
              rect swallowing them. */}
          <rect
            x={plotLeft}
            y={plotTop}
            width={plotWidth}
            height={PLOT_HEIGHT}
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

          {eventPositionGroups.map((group) => {
            const totalItems = group.dateGroups.reduce((sum, g) => sum + g.items.length, 0)
            const allItems = group.dateGroups.flatMap((g) => g.items)
            const primaryColor = categoryColor(allItems[0].category)
            const label =
              totalItems === 1
                ? allItems[0].title
                : `${totalItems} events near ${dateFormatter.format(new Date(visible[group.idx].date))}`
            return (
              <g
                key={`event-${group.idx}`}
                className="cursor-pointer"
                onPointerEnter={() => {
                  setHoverIndex(group.idx)
                  setHoveredEvents(group)
                }}
                onPointerLeave={() => setHoveredEvents(null)}
                onClick={() => onEventMarkerClick?.(allItems)}
                role="button"
                aria-label={label}
              >
                <circle cx={group.x} cy={group.y} r={10} fill="transparent" />
                <circle
                  cx={group.x}
                  cy={group.y}
                  r={5.5}
                  fill={primaryColor}
                  stroke="#0f172a"
                  strokeWidth={1.5}
                />
                {totalItems > 1 && (
                  <text x={group.x} y={group.y} textAnchor="middle" dominantBaseline="middle" fontSize={7} fontWeight={700} fill="#0f172a">
                    {totalItems}
                  </text>
                )}
                {/* A second date landing on the same resolved trading
                    session as the primary one gets a small ring offset
                    so it stays individually visible — display-only, the
                    date itself is never changed. */}
                {group.dateGroups.slice(1).map((extra, layer) => (
                  <circle
                    key={extra.date}
                    cx={group.x + (layer + 1) * EVENT_LAYER_PX}
                    cy={group.y - (layer + 1) * EVENT_LAYER_PX}
                    r={3.5}
                    fill={categoryColor(extra.items[0].category)}
                    stroke="#0f172a"
                    strokeWidth={1}
                  />
                ))}
              </g>
            )
          })}
        </svg>

        {hoveredEventsValid && hoveredEvents && totalHoveredEvents > 0 && (
          <div
            className="pointer-events-none absolute z-10 w-56 rounded-md border border-slate-700 bg-slate-900 p-2.5 text-xs shadow-lg"
            style={{
              left: `${tooltipXPct}%`,
              top: `${tooltipYPct}%`,
              transform: `translate(${flipLeft ? '-100%' : '12px'}, ${flipDown ? '12px' : 'calc(-100% - 12px)'})`,
            }}
          >
            {totalHoveredEvents === 1 ? (
              <EventTooltipSingle event={allEventItems[0]} tradingDate={visible[hoveredEvents.idx].date} />
            ) : (
              <>
                <p className="font-medium text-slate-200">
                  {totalHoveredEvents} events on {dateFormatter.format(new Date(visible[hoveredEvents.idx].date))}
                </p>
                <ul className="mt-1 flex flex-col gap-0.5 text-slate-400">
                  {allEventItems.slice(0, 3).map((e) => (
                    <li key={e.id} className="flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: categoryColor(e.category) }} />
                      <span className="truncate">{e.title}</span>
                    </li>
                  ))}
                </ul>
                {totalHoveredEvents > 3 && <p className="mt-1 text-slate-500">+{totalHoveredEvents - 3} more</p>}
                <p className="mt-1.5 text-slate-500">Click to see all</p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function EventTooltipSingle({ event, tradingDate }: { event: StockEvent; tradingDate: string }) {
  const announcedDate = event.published_at.slice(0, 10)
  const differsFromTradingDay = announcedDate !== tradingDate

  return (
    <>
      <span
        className="inline-flex items-center gap-1 rounded-full border border-slate-700 px-1.5 py-0.5 text-[10px]"
        style={{ color: categoryColor(event.category) }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: categoryColor(event.category) }} />
        {categoryLabel(event.category)}
      </span>
      <p className="mt-1 font-medium text-slate-200">{truncate(event.title, 90)}</p>
      <p className="mt-0.5 text-slate-500">
        {fullDateFormatter.format(new Date(event.published_at))}
        {differsFromTradingDay && ' (non-trading day)'}
      </p>
      {event.summary && <p className="mt-1 text-slate-400">{truncate(event.summary, 110)}</p>}
      <p className="mt-1 text-slate-500">Source: {event.source_name}</p>
      <p className="mt-1.5 text-sky-400">Click for full details &amp; source link</p>
    </>
  )
}
