"""Pydantic schemas for the backtesting API."""

from datetime import date

from pydantic import BaseModel


class BacktestTrade(BaseModel):
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    return_pct: float
    holding_days: int
    is_open: bool


class EquityPoint(BaseModel):
    date: date
    close: float
    equity: float
    in_position: bool
    short_sma: float | None
    long_sma: float | None


class BacktestSummary(BaseModel):
    initial_capital: float
    final_equity: float
    total_return_pct: float
    buy_and_hold_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: float


class BacktestResponse(BaseModel):
    symbol: str
    exchange: str
    strategy: str
    interval: str
    short_window: int
    long_window: int
    start_date: date
    end_date: date
    lookback_bars: int
    warmup_complete_date: date | None
    is_fully_warmed_up: bool
    summary: BacktestSummary
    equity_curve: list[EquityPoint]
    trades: list[BacktestTrade]
