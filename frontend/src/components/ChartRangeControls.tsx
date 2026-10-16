interface Preset {
  label: string
  days: number | 'all'
}

const PRESETS: Preset[] = [
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: '6M', days: 182 },
  { label: '1Y', days: 365 },
  { label: '3Y', days: 1095 },
  { label: 'ALL', days: 'all' },
]

interface ChartRangeControlsProps {
  firstDate: string
  lastDate: string
  onSelectPreset: (days: number | 'all') => void
  onReset: () => void
  isZoomed: boolean
}

export default function ChartRangeControls({
  firstDate,
  lastDate,
  onSelectPreset,
  onReset,
  isZoomed,
}: ChartRangeControlsProps) {
  const totalSpanDays = (new Date(lastDate).getTime() - new Date(firstDate).getTime()) / 86_400_000

  return (
    <div className="flex flex-wrap items-center gap-1 text-xs">
      {PRESETS.map(({ label, days }) => {
        const disabled = days !== 'all' && days > totalSpanDays + 1
        return (
          <button
            key={label}
            type="button"
            disabled={disabled}
            onClick={() => onSelectPreset(days)}
            className="rounded-full border border-slate-700 px-2 py-0.5 text-slate-300 transition hover:border-slate-500 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-30"
            title={disabled ? 'Not enough data in this run for this range' : undefined}
          >
            {label}
          </button>
        )
      })}
      <button
        type="button"
        onClick={onReset}
        disabled={!isZoomed}
        className="ml-1 rounded-full border border-slate-700 px-2 py-0.5 text-slate-400 transition hover:border-slate-500 hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-30"
      >
        Reset zoom
      </button>
      <span className="ml-1 text-slate-600">Scroll to zoom · drag to pan</span>
    </div>
  )
}
