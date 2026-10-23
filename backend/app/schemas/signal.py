"""Pydantic schemas for signals, scan runs, and notification delivery."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.backtest import BacktestTrade


class SignalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_id: int
    symbol: str = ""
    scan_run_id: int | None
    strategy_name: str
    strategy_version: str
    session_date: date
    signal_type: str
    price: float
    indicators: dict[str, Any]
    data_quality_status: str
    notification_status: str
    generated_at: datetime

    @field_validator("indicators", mode="before")
    @classmethod
    def _parse_indicators(cls, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value


class SignalEventListResponse(BaseModel):
    items: list[SignalEventRead]
    total: int
    limit: int
    offset: int


class ScanRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    session_date: date
    strategy_name: str
    strategy_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    universe_size: int
    symbols_succeeded: int
    symbols_failed: int
    symbols_stale: int
    symbols_skipped: int
    buy_signals: int
    sell_signals: int
    error_message: str | None


class ScanRunListResponse(BaseModel):
    items: list[ScanRunRead]
    total: int
    limit: int
    offset: int


class SymbolScanOutcomeRead(BaseModel):
    symbol: str
    status: str
    signal_type: str | None
    data_quality: str | None
    error: str | None


class ManualScanResponse(BaseModel):
    scan_run_id: int
    status: str
    session_date: date
    universe_size: int
    symbols_succeeded: int
    symbols_failed: int
    symbols_stale: int
    symbols_skipped: int
    buy_signals: int
    sell_signals: int
    notifications_sent: int
    notifications_failed: int
    notifications_skipped_cap: int
    error_message: str | None
    data_quality_report: list[SymbolScanOutcomeRead]


class TelegramTestResponse(BaseModel):
    success: bool
    error: str | None


class StrategyConfigResponse(BaseModel):
    name: str
    version: str
    sma_short: int
    sma_mid: int
    sma_long: int
    momentum_short_days: int
    momentum_long_days: int
    volume_lookback: int
    volume_multiplier: float
    volatility_lookback: int
    max_staleness_days: int


class UniverseRefreshResponse(BaseModel):
    universe: str
    source_fetch_succeeded: bool
    records_seen: int
    created: int
    updated: int
    unchanged: int
    deactivated: int
    invalid_records: list[str]
    duplicate_symbols: list[str]
    error: str | None


class HybridBacktestSummary(BaseModel):
    initial_capital: float
    final_equity: float
    total_return_pct: float
    buy_and_hold_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    volatility_pct_annualized: float
    sharpe_ratio: float | None
    num_trades: int
    win_rate_pct: float
    avg_trade_return_pct: float
    exposure_pct: float
    turnover: int
    cost_bps: float


class HybridEquityPointRead(BaseModel):
    date: date
    close: float
    equity: float
    in_position: bool
    data_quality: str
    sma_mid: float | None
    sma_long: float | None


class HybridBacktestResponse(BaseModel):
    symbol: str
    exchange: str
    strategy: str
    start_date: date
    end_date: date
    lookback_bars: int
    warmup_complete_date: date | None
    is_fully_warmed_up: bool
    cost_model: str
    summary: HybridBacktestSummary
    equity_curve: list[HybridEquityPointRead]
    trades: list[BacktestTrade]
