"""Daily scan scheduling.

Uses APScheduler's `BackgroundScheduler` with a cron trigger pinned to
`Asia/Kolkata`, since the NSE session close is a wall-clock-local event,
not a UTC one, and should stay correct across DST-free IST regardless of
where the server itself runs.

This does **not** attempt to know the NSE trading calendar (which
sessions are holidays). It runs every weekday at the configured time;
`scan_service.run_scan` itself is calendar-agnostic too - if there is no
genuinely new completed session (e.g. the scan runs on a holiday),
`signal_service.scan_symbol` will find the latest stored bar is older
than `session_date` and correctly report it as `stale`, not fabricate a
signal from stale data. A real NSE holiday calendar would improve the
scan-run audit trail (fewer confusing "stale" counts on holidays) but is
not required for correctness.

Multi-worker safety: APScheduler's in-process trigger firing is not
itself cross-process safe - if this app is deployed with multiple
backend worker processes, *every* worker's APScheduler instance will fire
at the configured time. The DB-backed `scan_lock_service` lock, acquired
inside `scan_service.run_scan`, is what actually prevents a duplicate
concurrent scan; the losing worker's `run_scan` call simply raises
`ScanLockHeldError`, which is caught and logged here, not escalated.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.data.ingestion.yahoo_finance import YahooFinanceProvider
from app.services import scan_lock_service, scan_service
from app.services.scan_service import DEFAULT_CONFIG
from app.services.trading_calendar import latest_completed_session

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_scheduled_scan(settings: Settings) -> None:
    db = SessionLocal()
    try:
        session_date = latest_completed_session(
            timezone_name=settings.scheduler_timezone,
            post_close_delay_minutes=settings.scan_post_close_delay_minutes,
        )
        provider = YahooFinanceProvider()
        summary = scan_service.run_scan(
            db,
            provider,
            session_date,
            config=DEFAULT_CONFIG,
            trigger="scheduled",
            max_concurrent_symbols=settings.scan_max_concurrent_symbols,
            max_retries=settings.scan_max_retries,
            backoff_seconds=settings.scan_retry_backoff_seconds,
            max_notifications=settings.telegram_max_notifications_per_scan,
        )
        logger.info(
            "Scheduled scan finished: run_id=%s status=%s buy=%s sell=%s failed=%s",
            summary.scan_run_id,
            summary.status,
            summary.buy_signals,
            summary.sell_signals,
            summary.symbols_failed,
        )
    except scan_lock_service.ScanLockHeldError:
        logger.info("Scheduled scan skipped - another scan is already running.")
    except Exception:  # noqa: BLE001 - the scheduler thread must never die
        logger.exception("Scheduled scan failed with an unexpected error.")
    finally:
        db.close()


def start_scheduler(settings: Settings | None = None) -> BackgroundScheduler | None:
    """Start the background scheduler, or do nothing if disabled.

    Idempotent - calling this twice (e.g. under `--reload`) does not
    start two schedulers; the second call is a no-op.
    """
    global _scheduler
    settings = settings or get_settings()

    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false) - no automatic scans will run.")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        _run_scheduled_scan,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.scan_hour_ist,
            minute=settings.scan_minute_ist,
            timezone=settings.scheduler_timezone,
        ),
        args=[settings],
        id="daily_signal_scan",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started: daily scan at %02d:%02d %s on weekdays.",
        settings.scan_hour_ist,
        settings.scan_minute_ist,
        settings.scheduler_timezone,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
