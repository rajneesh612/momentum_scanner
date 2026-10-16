// Small "nice numbers" tick generator so chart gridlines land on round
// values instead of the raw data min/max.

function niceNumber(value: number, round: boolean): number {
  const exponent = Math.floor(Math.log10(value))
  const fraction = value / 10 ** exponent

  let niceFraction: number
  if (round) {
    if (fraction < 1.5) niceFraction = 1
    else if (fraction < 3) niceFraction = 2
    else if (fraction < 7) niceFraction = 5
    else niceFraction = 10
  } else {
    if (fraction <= 1) niceFraction = 1
    else if (fraction <= 2) niceFraction = 2
    else if (fraction <= 5) niceFraction = 5
    else niceFraction = 10
  }

  return niceFraction * 10 ** exponent
}

export interface NiceScale {
  min: number
  max: number
  ticks: number[]
}

export function niceScale(dataMin: number, dataMax: number, tickCount = 4): NiceScale {
  if (dataMin === dataMax) {
    const pad = Math.abs(dataMin) * 0.05 || 1
    dataMin -= pad
    dataMax += pad
  }

  const range = niceNumber(dataMax - dataMin, false)
  const step = niceNumber(range / (tickCount - 1), true)
  const min = Math.floor(dataMin / step) * step
  const max = Math.ceil(dataMax / step) * step

  const ticks: number[] = []
  for (let v = min; v <= max + step * 0.5; v += step) {
    ticks.push(Math.round(v * 100) / 100)
  }

  return { min, max, ticks }
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
