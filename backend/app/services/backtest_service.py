"""Backtest orchestration.

Bridges the persisted PriceHistory table and the framework-free momentum
backtest engine: fetches stored prices (with extra lookback so the moving
averages have room to warm up), runs the strategy, and hands back a plain
BacktestResult for the API layer to shape into a response.
"""

import contextlib
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.data.ingestion.provider import MarketDataProviderError
from app.models.stock import Stock
from app.momentum.backtest import BacktestResult, run_sma_crossover_backtest
from app.services.market_data_service import (
    MarketDataPersistenceError,
    MarketDataService,
    StockNotFoundError,
)

__all__ = ["NoBacktestDataError", "StockNotFoundError", "run_backtest"]


class NoBacktestDataError(Exception):
    """Raised when there is no synced price data in the requested window."""


# Rough calendar days per bar, used only to size the SMA warmup lookback
# window - doesn't need to be exact, just generous enough to usually cover
# `long_window` prior bars when they're already synced.
_CALENDAR_DAYS_PER_BAR = {"1d": 1.6, "1wk": 8, "1mo": 32}


def run_backtest(
    db: Session,
    service: MarketDataService,
    symbol: str,
    start_date: date,
    end_date: date,
    short_window: int,
    long_window: int,
    initial_capital: float,
    interval: str = "1d",
) -> tuple[Stock, BacktestResult]:
    """Fetch stored price history (with SMA warmup lookback) and backtest it.

    Opportunistically tops up missing history first, via the same sync
    path `POST /market-data/sync` uses, so a symbol that's never been
    manually synced (or wasn't synced far back enough for the long SMA to
    warm up) still produces a trustworthy result instead of silently
    running on an empty/partial signal. This is best-effort: if the top-up
    fails (rate limit, unknown symbol, network, DB hiccup), we fall
    through and use whatever is already stored — handled honestly below
    via `lookback_bars` / `is_fully_warmed_up`, not silently ignored.
    """
    days_per_bar = _CALENDAR_DAYS_PER_BAR.get(interval, 1.6)
    lookback_start = start_date - timedelta(days=int(long_window * days_per_bar) + 10)

    with contextlib.suppress(MarketDataProviderError, MarketDataPersistenceError):
        service.sync_symbol_history(db, symbol, lookback_start, end_date, interval)

    stock, prices = service.get_price_history(db, symbol, lookback_start, end_date, interval)

    has_data_in_window = any(start_date <= p.date <= end_date for p in prices)
    if not has_data_in_window:
        raise NoBacktestDataError(
            f"No historical price data found for '{symbol}' between {start_date} and {end_date}."
        )

    df = pd.DataFrame({"date": [p.date for p in prices], "close": [p.close for p in prices]})

    result = run_sma_crossover_backtest(
        df,
        start_date=start_date,
        end_date=end_date,
        short_window=short_window,
        long_window=long_window,
        initial_capital=initial_capital,
    )

    return stock, result
