"""SMA crossover backtesting engine.

Pure dataclasses/functions operating on a plain price DataFrame — no
FastAPI or database dependency, so this stays independently testable and
reusable outside the API. `app/services/backtest_service.py` is the only
place that bridges this to persisted PriceHistory rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass
class Trade:
    """A completed or still-open long position.

    For an open trade (`is_open=True`), `exit_date`/`exit_price` mark the
    position to the last simulated bar rather than a real exit signal.
    """

    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    is_open: bool

    @property
    def return_pct(self) -> float:
        return (self.exit_price / self.entry_price - 1) * 100

    @property
    def holding_days(self) -> int:
        return (self.exit_date - self.entry_date).days


@dataclass
class EquityPoint:
    date: date
    close: float
    equity: float
    in_position: bool
    # Exposed so the frontend can draw the actual SMA lines the strategy
    # traded on — None during warmup, when the average has no value yet.
    short_sma: float | None = None
    long_sma: float | None = None


@dataclass
class BacktestResult:
    equity_curve: list[EquityPoint]
    trades: list[Trade]
    initial_capital: float
    lookback_bars: int
    # First date in the evaluation window where the long SMA has a value
    # (enough prior bars existed). None if it never warms up at all within
    # the fetched data.
    warmup_complete_date: date | None = None

    @property
    def is_fully_warmed_up(self) -> bool:
        """True if the long SMA already had a value on day 1 of the
        evaluation window — i.e. no part of the window ran on a partial
        signal."""
        if self.warmup_complete_date is None or not self.equity_curve:
            return False
        return self.warmup_complete_date == self.equity_curve[0].date

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1].equity if self.equity_curve else self.initial_capital

    @property
    def total_return_pct(self) -> float:
        if self.initial_capital <= 0:
            return 0.0
        return (self.final_equity / self.initial_capital - 1) * 100

    @property
    def buy_and_hold_return_pct(self) -> float:
        if len(self.equity_curve) < 2 or self.equity_curve[0].close <= 0:
            return 0.0
        return (self.equity_curve[-1].close / self.equity_curve[0].close - 1) * 100

    @property
    def max_drawdown_pct(self) -> float:
        peak = float("-inf")
        max_dd = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak > 0:
                max_dd = min(max_dd, (point.equity - peak) / peak * 100)
        return max_dd

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if not t.is_open]

    @property
    def win_rate_pct(self) -> float:
        closed = self.closed_trades
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t.return_pct > 0)
        return wins / len(closed) * 100

    @property
    def cagr_pct(self) -> float:
        if len(self.equity_curve) < 2 or self.initial_capital <= 0:
            return 0.0
        days = (self.equity_curve[-1].date - self.equity_curve[0].date).days
        if days <= 0:
            return 0.0
        ratio = self.final_equity / self.initial_capital
        if ratio <= 0:
            return -100.0
        years = days / 365.25
        return (ratio ** (1 / years) - 1) * 100


def run_sma_crossover_backtest(
    prices: pd.DataFrame,
    start_date: date,
    end_date: date,
    short_window: int = 50,
    long_window: int = 200,
    initial_capital: float = 100_000.0,
) -> BacktestResult:
    """Long-only SMA crossover backtest, one position at a time.

    Goes long the bar the short SMA crosses above the long SMA, and exits
    the bar it crosses back below. `prices` (columns: `date`, `close`) may
    include rows before `start_date` purely so the moving averages are
    warmed up — only rows in [start_date, end_date] are simulated.
    """
    df = prices.sort_values("date").reset_index(drop=True)
    df["short_sma"] = df["close"].rolling(window=short_window).mean()
    df["long_sma"] = df["close"].rolling(window=long_window).mean()

    lookback_bars = int((df["date"] < start_date).sum())
    window = df[(df["date"] >= start_date) & (df["date"] <= end_date)]

    equity_curve: list[EquityPoint] = []
    trades: list[Trade] = []

    cash = initial_capital
    shares = 0.0
    entry_date: date | None = None
    entry_price: float | None = None
    prev_signal = False
    warmup_complete_date: date | None = None

    for _, row in window.iterrows():
        if warmup_complete_date is None and pd.notna(row["long_sma"]):
            warmup_complete_date = row["date"]

        signal = bool(
            pd.notna(row["short_sma"])
            and pd.notna(row["long_sma"])
            and row["short_sma"] > row["long_sma"]
        )

        if signal and not prev_signal and shares == 0:
            shares = cash / row["close"]
            cash = 0.0
            entry_date = row["date"]
            entry_price = row["close"]
        elif not signal and prev_signal and shares > 0:
            cash = shares * row["close"]
            trades.append(Trade(entry_date, entry_price, row["date"], row["close"], is_open=False))
            shares = 0.0
            entry_date = None
            entry_price = None

        short_sma_value = row["short_sma"] if pd.notna(row["short_sma"]) else None
        long_sma_value = row["long_sma"] if pd.notna(row["long_sma"]) else None
        equity_curve.append(
            EquityPoint(
                row["date"],
                row["close"],
                cash + shares * row["close"],
                shares > 0,
                short_sma_value,
                long_sma_value,
            )
        )
        prev_signal = signal

    if shares > 0 and entry_date is not None and entry_price is not None:
        last_row = window.iloc[-1]
        trades.append(
            Trade(entry_date, entry_price, last_row["date"], last_row["close"], is_open=True)
        )

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        initial_capital=initial_capital,
        lookback_bars=lookback_bars,
        warmup_complete_date=warmup_complete_date,
    )
