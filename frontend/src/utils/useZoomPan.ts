import { useEffect, useRef, useState } from 'react'

import {
  computePan,
  computePresetRange,
  computeZoom,
  datasetSignature,
  fullRange,
  rangeLength,
  type ZoomRange,
} from './zoomMath'

// There is no charting library in this app (PriceSmaChart/EquityCurveChart
// are hand-rolled inline SVG) — this hook implements zoom/pan natively as
// an index window [start, end] (inclusive) into the full data array. Every
// series (price, SMA, trade markers, event markers) is sliced from the
// same window, so they always stay aligned to the same dates. All the
// actual index math lives in `zoomMath.ts` (pure, unit-tested); this hook
// is just a React-state wrapper around it.

export type { ZoomRange } from './zoomMath'

interface UseZoomPanOptions {
  length: number
  minVisible?: number
  /** Identifies the dataset beyond just its length (e.g. first/last
   * date) — pass this so a same-length-but-different-data change (new
   * symbol, same date count) also resets the zoom, not just a length
   * change. */
  firstDate?: string
  lastDate?: string
}

export interface ZoomPanControls {
  range: ZoomRange
  isZoomed: boolean
  isPanning: boolean
  zoomAt: (centerIndex: number, factor: number) => void
  startPan: (clientX: number) => void
  updatePan: (clientX: number, pixelsPerIndex: number) => void
  endPan: () => void
  setPresetDays: (days: number | 'all', dateAt: (i: number) => string) => void
  reset: () => void
}

export function useZoomPan({ length, minVisible = 3, firstDate, lastDate }: UseZoomPanOptions): ZoomPanControls {
  const [range, setRange] = useState<ZoomRange>(() => fullRange(length))
  const [isPanning, setIsPanning] = useState(false)
  const signature = datasetSignature(length, firstDate, lastDate)
  const prevSignature = useRef(signature)
  const panStartClientX = useRef(0)
  const panStartRange = useRef<ZoomRange>(fullRange(length))

  // A new/different backtest result (length OR dates changed) — snap back
  // to the full view rather than risk an out-of-range slice.
  useEffect(() => {
    if (prevSignature.current !== signature) {
      setRange(fullRange(length))
      prevSignature.current = signature
    }
  }, [signature, length])

  function zoomAt(centerIndex: number, factor: number) {
    setRange((r) => computeZoom(r, centerIndex, factor, length, minVisible))
  }

  function startPan(clientX: number) {
    panStartClientX.current = clientX
    panStartRange.current = range
    setIsPanning(true)
  }

  function updatePan(clientX: number, pixelsPerIndex: number) {
    if (!isPanning || !(pixelsPerIndex > 0)) return
    const deltaPx = clientX - panStartClientX.current
    const deltaIndex = Math.round(deltaPx / pixelsPerIndex)
    setRange(computePan(panStartRange.current, deltaIndex, length, minVisible))
  }

  function endPan() {
    setIsPanning(false)
  }

  function setPresetDays(days: number | 'all', dateAt: (i: number) => string) {
    setRange(computePresetRange(length, days, dateAt))
  }

  function reset() {
    setRange(fullRange(length))
  }

  return {
    range,
    isZoomed: rangeLength(range) < length,
    isPanning,
    zoomAt,
    startPan,
    updatePan,
    endPan,
    setPresetDays,
    reset,
  }
}

// Re-exported for components that want to validate/clamp a stale/local
// index (e.g. a hover index or a tooltip's anchor index) against the
// current visible-slice length without importing zoomMath directly.
export { clampIndex, clampRange, isValidIndex } from './zoomMath'
