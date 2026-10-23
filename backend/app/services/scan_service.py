"""Full-universe daily scan orchestration.

Ties together, in order: the DB-backed lock (so two workers never scan
concurrently), a `ScanRun` audit row, per-symbol evaluation via
`signal_service.scan_symbol` (run with bounded concurrency - each worker
thread uses its own DB session, since SQLAlchemy sessions are not
thread-safe), and finally Telegram dispatch for whatever fresh signals
were just created, capped at `max_notifications`.

Called by both the scheduler (`app/scheduler.py`, trigger="scheduled")
and the manual-trigger API route (trigger="manual") - same code path, so
there is exactly one way a scan can happen, not two parallel
implementations that could silently drift apart.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.data.ingestion.provider import MarketDataProvider
from app.models.scan_run import ScanRun
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.momentum.hybrid_signal import HybridStrategyConfig
from app.services import notification_service, scan_lock_service, universe_service
from app.services.market_data_service import MarketDataService
from app.services.signal_service import SymbolScanOutcome, scan_symbol

DEFAULT_CONFIG = HybridStrategyConfig()


@dataclass
class ScanSummary:
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
    error_message: str | None = None
    outcomes: list[SymbolScanOutcome] = field(default_factory=list)


def _scan_one(
    symbol_stock_id: int,
    provider: MarketDataProvider,
    config: HybridStrategyConfig,
    session_date: date,
    scan_run_id: int,
    max_retries: int,
    backoff_seconds: float,
) -> SymbolScanOutcome:
    thread_db = SessionLocal()
    try:
        stock = thread_db.get(Stock, symbol_stock_id)
        if stock is None:
            return SymbolScanOutcome(
                symbol=f"<id {symbol_stock_id}>", status="error", error="Stock no longer exists."
            )
        service = MarketDataService(provider)
        return scan_symbol(
            thread_db,
            service,
            stock,
            config,
            session_date,
            scan_run_id=scan_run_id,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
        )
    except Exception as exc:  # noqa: BLE001 - one symbol's failure must never kill the scan
        return SymbolScanOutcome(symbol=f"<id {symbol_stock_id}>", status="error", error=str(exc))
    finally:
        thread_db.close()


def run_scan(
    db: Session,
    provider: MarketDataProvider,
    session_date: date,
    config: HybridStrategyConfig = DEFAULT_CONFIG,
    trigger: str = "scheduled",
    max_concurrent_symbols: int = 5,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
    max_notifications: int = 20,
) -> ScanSummary:
    """Run one full-universe scan. Raises ScanLockHeldError (propagated
    from `scan_lock_service`) if a scan is already in progress - callers
    decide how to surface that (e.g. the manual-trigger route returns 409)."""
    with scan_lock_service.scan_lock(db):
        run = ScanRun(
            trigger=trigger,
            session_date=session_date,
            strategy_name=config.name,
            strategy_version=config.version,
            status="running",
        )
        db.add(run)
        db.commit()

        try:
            universe = universe_service.active_universe(db)
            run.universe_size = len(universe)
            db.commit()

            outcomes: list[SymbolScanOutcome] = []
            with ThreadPoolExecutor(max_workers=max(1, max_concurrent_symbols)) as pool:
                futures = {
                    pool.submit(
                        _scan_one,
                        stock.id,
                        provider,
                        config,
                        session_date,
                        run.id,
                        max_retries,
                        backoff_seconds,
                    ): stock.symbol
                    for stock in universe
                }
                for future in as_completed(futures):
                    outcomes.append(future.result())

            signal_statuses = ("signal", "ok_no_signal")
            skipped_statuses = ("insufficient", "missing")
            run.symbols_succeeded = sum(1 for o in outcomes if o.status in signal_statuses)
            run.symbols_failed = sum(1 for o in outcomes if o.status == "error")
            run.symbols_stale = sum(1 for o in outcomes if o.status == "stale")
            run.symbols_skipped = sum(1 for o in outcomes if o.status in skipped_statuses)
            run.buy_signals = sum(1 for o in outcomes if o.signal_type == "BUY")
            run.sell_signals = sum(1 for o in outcomes if o.signal_type == "SELL")

            if run.universe_size == 0:
                run.status = "failed"
                run.error_message = "Active universe is empty - has it been imported/refreshed?"
            elif run.symbols_failed == 0:
                run.status = "success"
            elif run.symbols_succeeded > 0:
                run.status = "partial_failure"
            else:
                run.status = "failed"
                run.error_message = "Every symbol in the universe failed to scan."

            run.finished_at = datetime.now(UTC)
            db.commit()

            notif_sent, notif_failed, notif_skipped = _dispatch_notifications(
                db, run.id, config, max_notifications, backoff_seconds
            )

            return ScanSummary(
                scan_run_id=run.id,
                status=run.status,
                session_date=session_date,
                universe_size=run.universe_size,
                symbols_succeeded=run.symbols_succeeded,
                symbols_failed=run.symbols_failed,
                symbols_stale=run.symbols_stale,
                symbols_skipped=run.symbols_skipped,
                buy_signals=run.buy_signals,
                sell_signals=run.sell_signals,
                notifications_sent=notif_sent,
                notifications_failed=notif_failed,
                notifications_skipped_cap=notif_skipped,
                error_message=run.error_message,
                outcomes=outcomes,
            )
        except Exception as exc:  # noqa: BLE001 - always finalize the run row, even on failure
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.finished_at = datetime.now(UTC)
            db.commit()
            raise


def _dispatch_notifications(
    db: Session,
    scan_run_id: int,
    config: HybridStrategyConfig,
    max_notifications: int,
    backoff_seconds: float,
) -> tuple[int, int, int]:
    from sqlalchemy import select

    pending = db.scalars(
        select(SignalEvent)
        .where(SignalEvent.scan_run_id == scan_run_id, SignalEvent.notification_status == "pending")
        .order_by(SignalEvent.id)
    ).all()

    sent = 0
    failed = 0
    skipped = max(0, len(pending) - max_notifications)
    for event in pending[:max_notifications]:
        symbol = event.stock.symbol
        outcome = notification_service.deliver(
            db, event, symbol, config, backoff_seconds=backoff_seconds
        )
        if outcome.success:
            sent += 1
        else:
            failed += 1

    return sent, failed, skipped
