// Pure index-window math for chart zoom/pan — no React, no DOM, so it's
// directly unit-testable. `useZoomPan.ts` is a thin React-state wrapper
// around these functions. A "range" is an inclusive [start, end] index
// window into a data array of a given `length`.
//
// `length <= 0` (no data) is represented by the empty-range sentinel
// { start: 0, end: -1} — consumers must treat end < start as "no visible
// points" and render an explicit empty state, never index into the array.

export interface ZoomRange {
  start: number
  end: number
}

export const EMPTY_RANGE: ZoomRange = { start: 0, end: -1 }

export function fullRange(length: number): ZoomRange {
  if (length <= 0) return EMPTY_RANGE
  return { start: 0, end: length - 1 }
}

export function rangeLength(range: ZoomRange): number {
  return Math.max(0, range.end - range.start + 1)
}

/** Clamp an arbitrary [start, end] pair into a valid window for `length`. */
export function clampRange(start: number, end: number, length: number, minVisible = 3): ZoomRange {
  if (length <= 0) return EMPTY_RANGE
  if (!Number.isFinite(start) || !Number.isFinite(end)) return fullRange(length)

  const maxIndex = length - 1
  // Never ask for a window wider than the data itself.
  const floor = Math.min(Math.max(1, minVisible - 1), maxIndex)

  let s = Math.round(start)
  let e = Math.round(end)
  if (e < s) e = s // never allow a reversed window

  // Enforce the minimum-width floor, anchored on the original center.
  if (e - s < floor) {
    const center = (s + e) / 2
    s = Math.round(center - floor / 2)
    e = s + floor
  }

  // Slide the whole window back into [0, maxIndex] without resizing it.
  const width = e - s
  if (s < 0) {
    s = 0
    e = width
  }
  if (e > maxIndex) {
    e = maxIndex
    s = e - width
  }
  s = Math.max(0, s)
  e = Math.min(maxIndex, e)
  if (e < s) e = s

  return { start: s, end: e }
}

/** Zoom the range in/out by `factor` (<1 zooms in, >1 zooms out), keeping
 * `centerIndex` (a full-dataset index) fixed under the cursor. */
export function computeZoom(
  range: ZoomRange,
  centerIndex: number,
  factor: number,
  length: number,
  minVisible = 3,
): ZoomRange {
  if (length <= 0) return EMPTY_RANGE
  if (!Number.isFinite(centerIndex) || !Number.isFinite(factor) || factor <= 0) return range

  const width = range.end - range.start
  const newWidth = Math.max(minVisible - 1, Math.min(length - 1, Math.round(width * factor)))
  const ratio = width <= 0 ? 0.5 : (centerIndex - range.start) / width
  const start = Math.round(centerIndex - newWidth * ratio)
  return clampRange(start, start + newWidth, length, minVisible)
}

/** Shift the range by `delta` indices (positive = later dates), keeping its width. */
export function computePan(range: ZoomRange, delta: number, length: number, minVisible = 3): ZoomRange {
  if (length <= 0) return EMPTY_RANGE
  if (!Number.isFinite(delta)) return range
  return clampRange(range.start - delta, range.end - delta, length, minVisible)
}

/** Resolve a "last N calendar days" preset to an index range, using the
 * actual dates in the dataset (`dateAt`) rather than assuming daily bars. */
export function computePresetRange(length: number, days: number | 'all', dateAt: (i: number) => string): ZoomRange {
  if (length <= 0) return EMPTY_RANGE
  if (days === 'all') return fullRange(length)

  const lastDate = new Date(dateAt(length - 1))
  const target = new Date(lastDate)
  target.setDate(target.getDate() - days)
  const targetStr = target.toISOString().slice(0, 10)

  let start = 0
  for (let i = 0; i < length; i++) {
    start = i
    if (dateAt(i) >= targetStr) break
  }
  return { start, end: length - 1 }
}

/** A stable signature that changes whenever the underlying dataset's
 * identity changes (not just its length) — used to decide when a zoom
 * range should snap back to the full view. */
export function datasetSignature(length: number, firstDate: string | undefined, lastDate: string | undefined): string {
  return `${length}:${firstDate ?? ''}:${lastDate ?? ''}`
}

/** Clamp a (possibly stale/out-of-range) local index into `[0, length-1]`,
 * or null if there's nothing to point at. Use this at every render before
 * indexing into a zoom-sliced array with a hover/cursor index. */
export function clampIndex(index: number | null, length: number): number | null {
  if (index === null || length <= 0) return null
  if (!Number.isFinite(index)) return null
  return Math.min(Math.max(0, Math.round(index)), length - 1)
}

/** Whether a (possibly stale) local index still refers to a real element
 * in an array of the given length. Any component state that captured an
 * index into a zoom-sliced array (e.g. "which point is this tooltip
 * anchored to") must be re-validated with this before every render that
 * indexes into the *current* slice — the slice is re-sliced on every
 * zoom/pan, but a `useState` value referencing an old index is not
 * automatically invalidated just because the array shrank. Prefer this
 * (hide/ignore stale state) over `clampIndex` (snap to nearest valid)
 * when showing content *at the wrong position* would be misleading
 * rather than merely imprecise — e.g. a tooltip for one specific point,
 * as opposed to a crosshair that may reasonably fall back to the nearest
 * point. */
export function isValidIndex(index: number | null | undefined, length: number): boolean {
  return index !== null && index !== undefined && Number.isFinite(index) && index >= 0 && index < length
}
