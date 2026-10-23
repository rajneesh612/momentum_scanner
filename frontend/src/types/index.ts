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

// --- Daily NIFTY 500 hybrid signal scanner ---

export type SignalType = 'BUY' | 'SELL'
export type DataQualityStatus = 'ok' | 'insufficient' | 'stale' | 'missing'
export type NotificationStatus = 'not_applicable' | 'pending' | 'sent' | 'failed'
export type ScanRunStatus = 'running' | 'success' | 'partial_failure' | 'failed'

export interface SignalEvent {
  id: number
  stock_id: number
  symbol: string
  scan_run_id: number | null
  strategy_name: string
  strategy_version: string
  session_date: string
  signal_type: SignalType
  price: number
  indicators: Record<string, number | null>
  data_quality_status: DataQualityStatus
  notification_status: NotificationStatus
  generated_at: string
}

export interface SignalEventListResponse {
  items: SignalEvent[]
  total: number
  limit: number
  offset: number
}

export interface ScanRun {
  id: number
  trigger: 'scheduled' | 'manual'
  session_date: string
  strategy_name: string
  strategy_version: string
  status: ScanRunStatus
  started_at: string
  finished_at: string | null
  universe_size: number
  symbols_succeeded: number
  symbols_failed: number
  symbols_stale: number
  symbols_skipped: number
  buy_signals: number
  sell_signals: number
  error_message: string | null
}

export interface StrategyConfig {
  name: string
  version: string
  sma_short: number
  sma_mid: number
  sma_long: number
  momentum_short_days: number
  momentum_long_days: number
  volume_lookback: number
  volume_multiplier: number
  volatility_lookback: number
  max_staleness_days: number
}

export interface SymbolScanOutcome {
  symbol: string
  status: string
  signal_type: SignalType | null
  data_quality: string | null
  error: string | null
}

export interface ManualScanResponse {
  scan_run_id: number
  status: ScanRunStatus
  session_date: string
  universe_size: number
  symbols_succeeded: number
  symbols_failed: number
  symbols_stale: number
  symbols_skipped: number
  buy_signals: number
  sell_signals: number
  notifications_sent: number
  notifications_failed: number
  notifications_skipped_cap: number
  error_message: string | null
  data_quality_report: SymbolScanOutcome[]
}

export interface TelegramTestResponse {
  success: boolean
  error: string | null
}
