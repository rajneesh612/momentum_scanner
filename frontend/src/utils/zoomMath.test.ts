import { describe, expect, it } from 'vitest'

import {
  clampIndex,
  clampRange,
  computePan,
  computePresetRange,
  computeZoom,
  datasetSignature,
  fullRange,
  isValidIndex,
  rangeLength,
} from './zoomMath'

describe('clampRange', () => {
  it('returns the full range unchanged when already valid', () => {
    expect(clampRange(0, 9, 10)).toEqual({ start: 0, end: 9 })
  })

  it('fixes a reversed start/end without crashing or returning empty', () => {
    const r = clampRange(8, 2, 10)
    expect(r.end).toBeGreaterThanOrEqual(r.start)
  })

  it('clamps a start/end that overshoots past the end of the dataset', () => {
    const r = clampRange(5, 1000, 10)
    expect(r.start).toBeGreaterThanOrEqual(0)
    expect(r.end).toBeLessThanOrEqual(9)
    expect(r.end).toBeGreaterThanOrEqual(r.start)
  })

  it('clamps a start that is far negative', () => {
    const r = clampRange(-1000, 5, 10)
    expect(r.start).toBeGreaterThanOrEqual(0)
    expect(r.end).toBeLessThanOrEqual(9)
    expect(r.end).toBeGreaterThanOrEqual(r.start)
  })

  it('handles a zero-length dataset by returning the empty sentinel', () => {
    const r = clampRange(0, 5, 0)
    expect(r.end).toBeLessThan(r.start)
    expect(rangeLength(r)).toBe(0)
  })

  it('handles a one-point dataset without throwing', () => {
    const r = clampRange(0, 5, 1)
    expect(r.start).toBe(0)
    expect(r.end).toBe(0)
  })

  it('handles a very small dataset (2-3 points) within bounds', () => {
    for (const length of [1, 2, 3]) {
      const r = clampRange(-5, 50, length)
      expect(r.start).toBeGreaterThanOrEqual(0)
      expect(r.end).toBeLessThanOrEqual(length - 1)
      expect(r.end).toBeGreaterThanOrEqual(r.start)
    }
  })

  it('never produces NaN or Infinity for extreme inputs', () => {
    const r = clampRange(-1e9, 1e9, 500)
    expect(Number.isFinite(r.start)).toBe(true)
    expect(Number.isFinite(r.end)).toBe(true)
  })

  it('treats non-finite start/end as a request for the full range', () => {
    expect(clampRange(Number.NaN, 5, 10)).toEqual(fullRange(10))
    expect(clampRange(0, Number.POSITIVE_INFINITY, 10)).toEqual(fullRange(10))
  })

  it('enforces a minimum visible width when the requested window is too narrow', () => {
    const r = clampRange(5, 5, 100, 5)
    expect(rangeLength(r)).toBeGreaterThanOrEqual(4)
  })

  it('never requests a window wider than the dataset itself', () => {
    const r = clampRange(0, 0, 3, 10)
    expect(rangeLength(r)).toBeLessThanOrEqual(3)
  })
})

describe('computeZoom', () => {
  it('zooms in around the cursor, shrinking the visible window', () => {
    const start = fullRange(100)
    const zoomedIn = computeZoom(start, 50, 0.5, 100)
    expect(rangeLength(zoomedIn)).toBeLessThan(rangeLength(start))
    expect(zoomedIn.start).toBeGreaterThanOrEqual(0)
    expect(zoomedIn.end).toBeLessThanOrEqual(99)
  })

  it('zooms out, growing the visible window up to the full dataset', () => {
    const narrow = { start: 40, end: 60 }
    const zoomedOut = computeZoom(narrow, 50, 2, 100)
    expect(rangeLength(zoomedOut)).toBeGreaterThan(rangeLength(narrow))
  })

  it('repeated zoom-in converges on the minimum window and stays valid', () => {
    let range = fullRange(200)
    for (let i = 0; i < 50; i++) {
      range = computeZoom(range, 100, 0.5, 200)
      expect(range.start).toBeGreaterThanOrEqual(0)
      expect(range.end).toBeLessThanOrEqual(199)
      expect(range.end).toBeGreaterThanOrEqual(range.start)
    }
    expect(rangeLength(range)).toBeGreaterThanOrEqual(2)
  })

  it('repeated zoom-out converges on the full dataset and stays valid', () => {
    let range = { start: 98, end: 100 }
    for (let i = 0; i < 50; i++) {
      range = computeZoom(range, 99, 2, 200)
    }
    expect(range).toEqual(fullRange(200))
  })

  it('handles an out-of-range cursor index gracefully', () => {
    const r = computeZoom(fullRange(50), 99999, 0.5, 50)
    expect(r.start).toBeGreaterThanOrEqual(0)
    expect(r.end).toBeLessThanOrEqual(49)
  })

  it('is a no-op for an empty dataset', () => {
    expect(computeZoom(fullRange(0), 0, 0.5, 0)).toEqual(fullRange(0))
  })

  it('ignores a non-finite or non-positive zoom factor', () => {
    const start = fullRange(100)
    expect(computeZoom(start, 50, Number.NaN, 100)).toEqual(start)
    expect(computeZoom(start, 50, 0, 100)).toEqual(start)
    expect(computeZoom(start, 50, -1, 100)).toEqual(start)
  })

  it('never produces NaN when the current range has zero width', () => {
    const r = computeZoom({ start: 10, end: 10 }, 10, 0.5, 100)
    expect(Number.isFinite(r.start)).toBe(true)
    expect(Number.isFinite(r.end)).toBe(true)
  })
})

describe('computePan', () => {
  it('shifts the range by the given index delta', () => {
    const r = computePan({ start: 10, end: 20 }, 5, 100)
    expect(r).toEqual({ start: 5, end: 15 })
  })

  it('clamps panning past the start of the dataset', () => {
    // Positive delta shifts the window toward earlier indices.
    const r = computePan({ start: 2, end: 12 }, 20, 100)
    expect(r.start).toBe(0)
    expect(rangeLength(r)).toBe(11)
  })

  it('clamps panning past the end of the dataset', () => {
    // Negative delta shifts the window toward later indices.
    const r = computePan({ start: 80, end: 90 }, -50, 100)
    expect(r.end).toBe(99)
    expect(rangeLength(r)).toBe(11)
  })

  it('preserves window width while panning', () => {
    const start = { start: 10, end: 30 }
    const panned = computePan(start, 3, 1000)
    expect(rangeLength(panned)).toBe(rangeLength(start))
  })
})

describe('computePresetRange', () => {
  const dateAt = (i: number) => {
    const d = new Date('2024-01-01')
    d.setDate(d.getDate() + i)
    return d.toISOString().slice(0, 10)
  }

  it('resolves "all" to the full range', () => {
    expect(computePresetRange(365, 'all', dateAt)).toEqual(fullRange(365))
  })

  it('resolves a day-count preset to a window ending at the last index', () => {
    const r = computePresetRange(365, 30, dateAt)
    expect(r.end).toBe(364)
    expect(r.start).toBeGreaterThan(0)
    expect(r.start).toBeLessThan(r.end)
  })

  it('clamps a preset longer than the available data to the full range', () => {
    const r = computePresetRange(10, 3650, dateAt)
    expect(r).toEqual({ start: 0, end: 9 })
  })

  it('handles an empty dataset', () => {
    expect(computePresetRange(0, 30, dateAt)).toEqual(fullRange(0))
  })
})

describe('datasetSignature', () => {
  it('differs when length differs', () => {
    expect(datasetSignature(10, 'a', 'b')).not.toBe(datasetSignature(11, 'a', 'b'))
  })

  it('differs when dates differ at the same length', () => {
    expect(datasetSignature(10, '2024-01-01', '2024-01-10')).not.toBe(
      datasetSignature(10, '2024-02-01', '2024-02-10'),
    )
  })

  it('is stable for identical inputs', () => {
    expect(datasetSignature(10, 'a', 'b')).toBe(datasetSignature(10, 'a', 'b'))
  })
})

describe('clampIndex', () => {
  it('passes through a valid index unchanged', () => {
    expect(clampIndex(5, 10)).toBe(5)
  })

  it('clamps an index past the end of the (possibly shrunk) array', () => {
    expect(clampIndex(500, 10)).toBe(9)
  })

  it('clamps a negative index to zero', () => {
    expect(clampIndex(-5, 10)).toBe(0)
  })

  it('returns null for a null index', () => {
    expect(clampIndex(null, 10)).toBeNull()
  })

  it('returns null when the array is empty', () => {
    expect(clampIndex(3, 0)).toBeNull()
  })

  it('returns null for a non-finite index', () => {
    expect(clampIndex(Number.NaN, 10)).toBeNull()
    expect(clampIndex(Number.POSITIVE_INFINITY, 10)).toBeNull()
  })
})

describe('isValidIndex', () => {
  it('accepts an index within bounds', () => {
    expect(isValidIndex(5, 10)).toBe(true)
    expect(isValidIndex(0, 10)).toBe(true)
    expect(isValidIndex(9, 10)).toBe(true)
  })

  it('rejects an index at or past the length', () => {
    expect(isValidIndex(10, 10)).toBe(false)
    expect(isValidIndex(500, 10)).toBe(false)
  })

  it('rejects a negative index', () => {
    expect(isValidIndex(-1, 10)).toBe(false)
  })

  it('rejects null/undefined', () => {
    expect(isValidIndex(null, 10)).toBe(false)
    expect(isValidIndex(undefined, 10)).toBe(false)
  })

  it('rejects non-finite values', () => {
    expect(isValidIndex(Number.NaN, 10)).toBe(false)
    expect(isValidIndex(Number.POSITIVE_INFINITY, 10)).toBe(false)
  })

  it('rejects any index once the length is zero', () => {
    expect(isValidIndex(0, 0)).toBe(false)
  })
})

describe('white-screen regression: stale hover/tooltip index after a zoom shrinks the visible slice', () => {
  // This is the exact mechanism that caused the reported crash: a
  // component captures `idx` (a local index into `visible`) in state
  // when the user hovers a marker, then the user zooms without first
  // moving the pointer away. `visible` is re-sliced to a new, usually
  // shorter, length — but the captured `idx` is not automatically
  // updated. Indexing into the new slice with the stale `idx` must never
  // happen; `isValidIndex` is what the component checks before doing so.
  it('a hover index captured against a wide range becomes invalid after zooming in', () => {
    const length = 365
    const wideRange = fullRange(length)
    const wideVisibleLength = rangeLength(wideRange)

    // User hovers near the right edge of the full (wide) view.
    const capturedIdx = wideVisibleLength - 5

    // Then zooms in several times at that same screen position without
    // moving the pointer - exactly reproducing "repeated wheel scrolling
    // ... becomes white" from a fixed cursor position.
    let range = wideRange
    for (let i = 0; i < 10; i++) {
      const visibleLength = rangeLength(range)
      const centerIndex = range.start + (visibleLength - 1)
      range = computeZoom(range, centerIndex, 0.8, length)
    }

    const newVisibleLength = rangeLength(range)
    expect(newVisibleLength).toBeLessThan(wideVisibleLength)

    // The captured index from before zooming must be recognized as
    // stale/invalid against the new, shorter slice - this is the check
    // that replaces an unguarded `visible[capturedIdx]` access.
    expect(isValidIndex(capturedIdx, newVisibleLength)).toBe(false)
  })

  it('an index re-derived fresh on every render is always valid for that render’s slice', () => {
    const length = 200
    let range = fullRange(length)
    for (let i = 0; i < 40; i++) {
      range = computeZoom(range, range.end, 0.8, length)
      const visibleLength = rangeLength(range)
      const freshIndex = visibleLength - 1 // e.g. "latest point in this render's slice"
      expect(isValidIndex(freshIndex, visibleLength)).toBe(true)
    }
  })
})

describe('repeated wheel-zoom regression (reproduces the reported scenario)', () => {
  function simulateWheelBurst(length: number, cursorT: number, ticks: number, factor: number) {
    let range = fullRange(length)
    for (let i = 0; i < ticks; i++) {
      const visibleLength = rangeLength(range)
      const localCenter = Math.round(cursorT * (visibleLength - 1))
      const globalCenter = range.start + localCenter
      range = computeZoom(range, globalCenter, factor, length)
      expect(Number.isFinite(range.start)).toBe(true)
      expect(Number.isFinite(range.end)).toBe(true)
      expect(range.end).toBeGreaterThanOrEqual(range.start)
      expect(range.start).toBeGreaterThanOrEqual(0)
      expect(range.end).toBeLessThanOrEqual(length - 1)
    }
    return range
  }

  it('stays valid zooming in repeatedly with the cursor pinned at the right edge', () => {
    const final = simulateWheelBurst(365, 1, 100, 0.8)
    expect(rangeLength(final)).toBeGreaterThanOrEqual(2)
  })

  it('stays valid zooming in repeatedly with the cursor pinned at the left edge', () => {
    const final = simulateWheelBurst(365, 0, 100, 0.8)
    expect(rangeLength(final)).toBeGreaterThanOrEqual(2)
  })

  it('stays valid zooming out repeatedly past the full dataset', () => {
    const final = simulateWheelBurst(365, 0.5, 100, 1.2)
    expect(final).toEqual(fullRange(365))
  })

  it('stays valid with rapid alternating zoom in/out at a fixed cursor', () => {
    let range = fullRange(365)
    for (let i = 0; i < 300; i++) {
      const factor = i % 2 === 0 ? 0.8 : 1.2
      range = computeZoom(range, 180, factor, 365)
      expect(Number.isFinite(range.start)).toBe(true)
      expect(Number.isFinite(range.end)).toBe(true)
      expect(range.end).toBeGreaterThanOrEqual(range.start)
    }
  })

  it('Reset Zoom after extensive zooming restores exactly the full dataset', () => {
    let range = fullRange(500)
    for (let i = 0; i < 60; i++) {
      const visibleLength = rangeLength(range)
      const localCenter = Math.round(0.8 * (visibleLength - 1))
      range = computeZoom(range, range.start + localCenter, 0.85, 500)
    }
    expect(rangeLength(range)).toBeLessThan(500)

    const reset = fullRange(500)
    expect(reset).toEqual({ start: 0, end: 499 })
    expect(rangeLength(reset)).toBe(500)
  })

  it('dragging (panning) beyond the dataset boundary after zooming stays valid', () => {
    let range = computeZoom(fullRange(300), 150, 0.3, 300)
    range = computePan(range, 10_000, 300) // drag far past the start
    expect(range.start).toBe(0)
    range = computePan(range, -10_000, 300) // drag far past the end
    expect(range.end).toBe(299)
  })
})
