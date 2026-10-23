"""Per-symbol hybrid-signal evaluation and persistence.

Bridges the persisted PriceHistory table and the framework-free
`app/momentum/hybrid_signal.py` engine, the same way
`app/services/backtest_service.py` bridges it for the SMA backtester.
`app/services/scan_service.py` calls `scan_symbol` once per active
universe symbol; this module never iterates the universe itself.

State durability: the "is this symbol currently in a BUY position"
question is answered by reading the most recent `SignalEvent` row for
(stock, strategy_name, strategy_version) from the database - never from
an in-memory variable - so a backend restart mid-universe, or a second
worker process, always sees the same state.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, timedelta

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.data.ingestion.provider import MarketDataProviderError
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.momentum.hybrid_signal import (
    DQ_OK,
    HybridEvaluation,
    HybridStrategyConfig,
    evaluate_latest,
)
from app.services.market_data_service import (
    MarketDataPersistenceError,
    MarketDataService,
    StockNotFoundError,
)

# Rough calendar days per daily bar, used only to size the fetch lookback
# window generously enough to cover `min_bars_required` prior sessions.
_CALENDAR_DAYS_PER_BAR = 1.6
_LOOKBACK_BUFFER_DAYS = 15

# Transient provider errors worth retrying with backoff - anything else
# (e.g. a malformed response we can't interpret) is not retried.
_RETRYABLE_EXCEPTIONS = (MarketDataProviderError, httpx.HTTPError, httpx.TimeoutException)


@dataclass
class SymbolScanOutcome:
    symbol: str
    status: str  # "signal" | "ok_no_signal" | "stale" | "insufficient" | "missing" | "error"
    signal_type: str | None = None
    data_quality: str | None = None
    last_available_date: date | None = None
    error: str | None = None


def _fetch_with_retry(
    service: MarketDataService,
    db: Session,
    symbol: str,
    start: date,
    end: date,
    interval: str,
    max_retries: int,
    backoff_seconds: float,
) -> None:
    """Best-effort top-up of stored price history, retried with backoff.

    Never raises on the final failure - the caller falls back to
    whatever is already stored, exactly like `backtest_service.run_backtest`
    does, and reports the shortfall honestly via SymbolScanOutcome instead
    of failing the whole scan for one bad symbol.
    """
    attempt = 0
    while True:
        try:
            service.sync_symbol_history(db, symbol, start, end, interval)
            return
        except _RETRYABLE_EXCEPTIONS:
            attempt += 1
            if attempt >= max_retries:
                return
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))
        except MarketDataPersistenceError:
            return


def scan_symbol(
    db: Session,
    service: MarketDataService,
    stock: Stock,
    config: HybridStrategyConfig,
    session_date: date,
    scan_run_id: int | None = None,
    interval: str = "1d",
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
) -> SymbolScanOutcome:
    """Evaluate one symbol for `session_date` and persist a SignalEvent
    if (and only if) a fresh BUY/SELL transition is detected."""
    lookback_start = session_date - timedelta(
        days=int(config.min_bars_required * _CALENDAR_DAYS_PER_BAR) + _LOOKBACK_BUFFER_DAYS
    )

    _fetch_with_retry(
        service,
        db,
        stock.symbol,
        lookback_start,
        session_date,
        interval,
        max_retries,
        backoff_seconds,
    )

    try:
        _, prices = service.get_price_history(
            db, stock.symbol, lookback_start, session_date, interval
        )
    except StockNotFoundError as exc:
        return SymbolScanOutcome(symbol=stock.symbol, status="error", error=str(exc))

    if not prices:
        return SymbolScanOutcome(symbol=stock.symbol, status="missing", data_quality="missing")

    df = pd.DataFrame(
        {
            "date": [p.date for p in prices],
            "close": [p.adjusted_close for p in prices],
            "volume": [p.volume for p in prices],
        }
    )

    in_position = _current_in_position(db, stock.id, config)

    evaluation: HybridEvaluation = evaluate_latest(df, config, in_position, session_date)

    outcome = SymbolScanOutcome(
        symbol=stock.symbol,
        status=_status_for(evaluation),
        data_quality=evaluation.data_quality,
        last_available_date=df["date"].max() if not df.empty else None,
    )

    if evaluation.signal is None:
        return outcome

    indicators = dict(evaluation.indicators)
    indicators["volume"] = evaluation.volume

    event = SignalEvent(
        stock_id=stock.id,
        scan_run_id=scan_run_id,
        strategy_name=config.name,
        strategy_version=config.version,
        session_date=session_date,
        signal_type=evaluation.signal,
        price=evaluation.close,
        indicators_json=json.dumps(indicators),
        data_quality_status=evaluation.data_quality,
        notification_status="pending",
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # Another (concurrent) scan already recorded this exact
        # (stock, strategy, session, signal_type) transition - not an
        # error, just a race we lost. No duplicate signal is created.
        db.rollback()
        outcome.status = "ok_no_signal"
        return outcome

    outcome.signal_type = evaluation.signal
    return outcome


def _status_for(evaluation: HybridEvaluation) -> str:
    if evaluation.signal is not None:
        return "signal"
    if evaluation.data_quality == DQ_OK:
        return "ok_no_signal"
    return evaluation.data_quality


def _current_in_position(db: Session, stock_id: int, config: HybridStrategyConfig) -> bool:
    """The strategy's state for this stock, derived purely from the most
    recent persisted SignalEvent - never from memory."""
    latest = db.scalar(
        select(SignalEvent)
        .where(
            SignalEvent.stock_id == stock_id,
            SignalEvent.strategy_name == config.name,
            SignalEvent.strategy_version == config.version,
        )
        .order_by(SignalEvent.session_date.desc(), SignalEvent.id.desc())
        .limit(1)
    )
    return latest is not None and latest.signal_type == "BUY"
