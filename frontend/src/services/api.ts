// Thin fetch wrapper for talking to the backend API.
//
// The frontend must never talk to a market-data provider (e.g. yfinance)
// directly — all data flows through this backend API layer.

import type {
  BacktestResponse,
  EventImpactResponse,
  HealthStatus,
  HistoricalPriceResponse,
  Interval,
  ManualScanResponse,
  MarketDataSyncResponse,
  ScanRun,
  SignalEventListResponse,
  StockEventListResponse,
  StockListResponse,
  StrategyConfig,
  TelegramTestResponse,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const API_V1_URL = `${API_BASE_URL}/api/v1`

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Response body wasn't JSON — fall through to statusText.
  }
  return response.statusText || `Request failed with status ${response.status}`
}

export interface ListStocksParams {
  q?: string
  isActive?: boolean
  limit?: number
  offset?: number
}

export async function listStocks(params: ListStocksParams = {}): Promise<StockListResponse> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.isActive !== undefined) query.set('is_active', String(params.isActive))
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.offset !== undefined) query.set('offset', String(params.offset))

  const response = await fetch(`${API_V1_URL}/stocks?${query.toString()}`)

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<StockListResponse>
}

export async function getHealth(): Promise<HealthStatus> {
  const response = await fetch(`${API_BASE_URL}/health`)

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<HealthStatus>
}

export async function syncSymbolHistory(
  symbol: string,
  startDate?: string,
  endDate?: string,
  interval: Interval = '1d',
): Promise<MarketDataSyncResponse> {
  const params = new URLSearchParams({ interval })
  if (startDate) params.set('start_date', startDate)
  if (endDate) params.set('end_date', endDate)

  const response = await fetch(
    `${API_V1_URL}/market-data/sync/${encodeURIComponent(symbol)}?${params.toString()}`,
    { method: 'POST' },
  )

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<MarketDataSyncResponse>
}

export async function getStockHistory(
  symbol: string,
  startDate: string,
  endDate: string,
  interval: Interval = '1d',
): Promise<HistoricalPriceResponse> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate, interval })

  const response = await fetch(
    `${API_V1_URL}/stocks/${encodeURIComponent(symbol)}/history?${params.toString()}`,
  )

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<HistoricalPriceResponse>
}

export interface BacktestParams {
  startDate: string
  endDate: string
  shortWindow: number
  longWindow: number
  initialCapital: number
  interval: Interval
}

export async function runBacktest(symbol: string, params: BacktestParams): Promise<BacktestResponse> {
  const query = new URLSearchParams({
    start_date: params.startDate,
    end_date: params.endDate,
    short_window: String(params.shortWindow),
    long_window: String(params.longWindow),
    initial_capital: String(params.initialCapital),
    interval: params.interval,
  })

  const response = await fetch(
    `${API_V1_URL}/backtest/${encodeURIComponent(symbol)}?${query.toString()}`,
    { method: 'POST' },
  )

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<BacktestResponse>
}

export interface ListStockEventsParams {
  startDate?: string
  endDate?: string
  category?: string
}

export async function listStockEvents(
  symbol: string,
  params: ListStockEventsParams = {},
): Promise<StockEventListResponse> {
  const query = new URLSearchParams()
  if (params.startDate) query.set('start_date', params.startDate)
  if (params.endDate) query.set('end_date', params.endDate)
  if (params.category) query.set('category', params.category)

  const response = await fetch(
    `${API_V1_URL}/stocks/${encodeURIComponent(symbol)}/events?${query.toString()}`,
  )

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<StockEventListResponse>
}

export async function getEventImpact(symbol: string, eventId: number): Promise<EventImpactResponse> {
  const response = await fetch(
    `${API_V1_URL}/stocks/${encodeURIComponent(symbol)}/events/${eventId}/impact`,
  )

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }

  return response.json() as Promise<EventImpactResponse>
}

// --- Daily NIFTY 500 hybrid signal scanner ---

export async function getLatestSignals(limit = 50): Promise<SignalEventListResponse> {
  const response = await fetch(`${API_V1_URL}/signals/latest?limit=${limit}`)
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return response.json() as Promise<SignalEventListResponse>
}

export async function getLatestScan(): Promise<ScanRun | null> {
  const response = await fetch(`${API_V1_URL}/scans/latest`)
  if (response.status === 404) return null
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return response.json() as Promise<ScanRun>
}

export async function listScans(limit = 20): Promise<{ items: ScanRun[]; total: number }> {
  const response = await fetch(`${API_V1_URL}/scans?limit=${limit}`)
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return response.json() as Promise<{ items: ScanRun[]; total: number }>
}

export async function getStrategyConfig(): Promise<StrategyConfig> {
  const response = await fetch(`${API_V1_URL}/strategy-config`)
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return response.json() as Promise<StrategyConfig>
}

export async function triggerManualScan(apiKey: string): Promise<ManualScanResponse> {
  const response = await fetch(`${API_V1_URL}/scans/run`, {
    method: 'POST',
    headers: { 'X-Scan-Api-Key': apiKey },
  })
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return response.json() as Promise<ManualScanResponse>
}

export async function sendTelegramTest(apiKey: string): Promise<TelegramTestResponse> {
  const response = await fetch(`${API_V1_URL}/telegram/test`, {
    method: 'POST',
    headers: { 'X-Scan-Api-Key': apiKey },
  })
  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status)
  }
  return response.json() as Promise<TelegramTestResponse>
}
