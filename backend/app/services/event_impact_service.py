"""Bridges persisted PriceHistory + StockEvent rows to the framework-free
event-impact calculator in `app/momentum/event_impact.py`.
"""

import contextlib
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.data.ingestion.provider import MarketDataProviderError
from app.models.stock_event import StockEvent
from app.momentum.event_impact import EventImpactResult, compute_event_impact
from app.services.market_data_service import (
    MarketDataPersistenceError,
    MarketDataService,
    StockNotFoundError,
)

DEFAULT_BENCHMARK_SYMBOL = "^NSEI"  # NIFTY 50 — just another Stock/PriceHistory row.

# Covers the longest window (120 trading days), with slack.
_LOOKAHEAD_CALENDAR_DAYS = int(120 * 1.6) + 15


def compute_impact_for_event(
    db: Session,
    service: MarketDataService,
    event: StockEvent,
    stock_symbol: str,
    today: date | None = None,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
) -> EventImpactResult:
    """Fetch (topping up where possible, best-effort) stock + benchmark
    price history around the event, then compute the post-event return
    windows. Never fabricates a window's values — see
    `app.momentum.event_impact` for the pending/unavailable rules.
    """
    today = today or date.today()
    event_date = event.published_at.date()
    range_end = min(today, event_date + timedelta(days=_LOOKAHEAD_CALENDAR_DAYS))

    with contextlib.suppress(MarketDataProviderError, MarketDataPersistenceError):
        service.sync_symbol_history(db, stock_symbol, event_date, range_end, "1d")

    _, stock_prices = service.get_price_history(db, stock_symbol, event_date, range_end, "1d")
    stock_series = [(p.date, p.close) for p in stock_prices]

    benchmark_series: list[tuple[date, float]] = []
    with contextlib.suppress(MarketDataProviderError, MarketDataPersistenceError):
        service.sync_symbol_history(db, benchmark_symbol, event_date, range_end, "1d")
    with contextlib.suppress(StockNotFoundError):
        _, bench_prices = service.get_price_history(
            db, benchmark_symbol, event_date, range_end, "1d"
        )
        benchmark_series = [(p.date, p.close) for p in bench_prices]

    return compute_event_impact(stock_series, benchmark_series, event_date, today)
