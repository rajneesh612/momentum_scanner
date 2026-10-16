import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ChartErrorBoundaryProps {
  children: ReactNode
  /** Shown in the fallback message, e.g. "Stock Price & SMA Signals". */
  chartName: string
}

interface ChartErrorBoundaryState {
  error: Error | null
}

// A safety net, not a substitute for fixing root causes: this exists so
// that an unexpected, not-yet-understood rendering error in one chart
// (now, or in the future) degrades to a recoverable message instead of
// permanently blanking the whole page — React error boundaries are the
// only mechanism that can catch a render-phase exception at all, and
// must be a class component (no hook equivalent exists). The error is
// always logged, never swallowed, so the real cause stays visible.
export default class ChartErrorBoundary extends Component<ChartErrorBoundaryProps, ChartErrorBoundaryState> {
  state: ChartErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ChartErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`Chart render error in "${this.props.chartName}":`, error, info.componentStack)
  }

  handleReset = (): void => {
    // Clearing the error re-renders `children` as a fresh mount, which
    // resets any internal state (zoom range, hover index, etc.) that may
    // have caused the crash.
    this.setState({ error: null })
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="flex flex-col items-center justify-center gap-2 rounded-md border border-rose-800/60 bg-rose-950/20 p-6 text-center text-sm text-rose-300">
          <p className="font-medium">Something went wrong rendering {this.props.chartName}.</p>
          <p className="max-w-md text-xs text-rose-400/80">{this.state.error.message}</p>
          <button
            type="button"
            onClick={this.handleReset}
            className="rounded-full border border-rose-700 px-3 py-1 text-xs text-rose-200 transition hover:border-rose-500"
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
