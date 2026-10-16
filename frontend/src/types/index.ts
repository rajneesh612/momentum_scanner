// Shared frontend TypeScript types.
//
// Domain types (WatchlistItem, ...) will be added here once the
// corresponding backend schemas exist.

export type Interval = '1d' | '1wk' | '1mo'

export interface Stock {
  id: number
  symbol: string
  name: string
  exchange: string
  sector: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface StockListResponse {
  items: Stock[]
  total: number
  limit: number
  offset: number
}

export interface HealthStatus {
  status: string
  app_name: string
  app_env: string
}

export interface PriceHistoryPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  adjusted_close: number
  volume: number
}

export interface HistoricalPriceResponse {
  symbol: string
  exchange: string
  interval: Interval
  start_date: string
  end_date: string
  count: number
  prices: PriceHistoryPoint[]
}

export interface MarketDataSyncResponse {
  symbol: string
  interval: Interval
  start_date: string
  end_date: string
  records_fetched: number
  records_created: number
  records_skipped: number
}

export interface BacktestTrade {
  entry_date: string
  entry_price: number
  exit_date: string
  exit_price: number
  return_pct: number
  holding_days: number
  is_open: boolean
}

export interface BacktestEquityPoint {
  date: string
  close: number
  equity: number
  in_position: boolean
  short_sma: number | null
  long_sma: number | null
}

export interface BacktestSummary {
  initial_capital: number
  final_equity: number
  total_return_pct: number
  buy_and_hold_return_pct: number
  cagr_pct: number
  max_drawdown_pct: number
  num_trades: number
  win_rate_pct: number
}

export type EventCategory =
  | 'earnings'
  | 'dividend'
  | 'buyback'
  | 'ma'
  | 'order_win'
  | 'regulatory'
  | 'fundraising'
  | 'other'

export interface StockEvent {
  id: number
  stock_id: number
  title: string
  category: EventCategory
  summary: string | null
  published_at: string
  source_name: string
  source_url: string
  provider: string
  verification_status: string
  ingested_at: string
}

export interface StockEventListResponse {
  symbol: string
  category: string | null
  count: number
  events: StockEvent[]
  news_unavailable: boolean
}

export interface EventImpactWindow {
  trading_days: number
  status: 'ok' | 'pending' | 'unavailable'
  stock_return_pct: number | null
  benchmark_return_pct: number | null
  relative_return_pct: number | null
  max_rise_pct: number | null
  max_drawdown_pct: number | null
}

export interface EventImpactResponse {
  event_id: number
  symbol: string
  event_date: string
  anchor_date: string | null
  benchmark_symbol: string
  benchmark_available: boolean
  windows: EventImpactWindow[]
  interpretation: string[]
}

export interface BacktestResponse {
  symbol: string
  exchange: string
  strategy: string
  interval: Interval
  short_window: number
  long_window: number
  start_date: string
  end_date: string
  lookback_bars: number
  warmup_complete_date: string | null
  is_fully_warmed_up: boolean
  summary: BacktestSummary
  equity_curve: BacktestEquityPoint[]
  trades: BacktestTrade[]
}
