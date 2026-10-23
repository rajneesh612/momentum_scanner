"""Tests for full-universe scan orchestration.

`scan_service` opens its own DB session per worker thread via
`app.core.database.SessionLocal` (SQLAlchemy sessions aren't thread-safe
to share) - these tests monkeypatch that name to a sessionmaker bound to
the *same* in-memory SQLite engine `db_session` uses (StaticPool keeps it
a single shared connection across threads), so worker threads see the
same test database instead of trying to reach a real Postgres.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.scan_lock import ScanLock
from app.models.scan_run import ScanRun
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.momentum.hybrid_signal import HybridStrategyConfig
from app.services import scan_lock_service, scan_service
from app.services.telegram_service import TelegramSendResult
from tests.fakes import FakeMarketDataProvider

_CONFIG = HybridStrategyConfig(
    sma_short=1,
    sma_mid=2,
    sma_long=3,
    momentum_short_days=1,
    momentum_long_days=2,
    volume_lookback=2,
    volume_multiplier=1.2,
    volatility_lookback=2,
    max_staleness_days=5,
)


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _bars(dates: list[date], closes: list[float], volumes: list[float]) -> list[dict]:
    return [
        {"date": d, "open": c, "high": c, "low": c, "close": c, "adjusted_close": c, "volume": v}
        for d, c, v in zip(dates, closes, volumes, strict=True)
    ]


@pytest.fixture
def patched_session_local(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    """Point scan_service's per-thread sessions at the test's in-memory DB."""
    test_sessionmaker = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(scan_service, "SessionLocal", test_sessionmaker)
    return test_sessionmaker


def _seed_buy_eligible_stock(db_session: Session, symbol: str = "AAA.NS") -> Stock:
    stock = Stock(symbol=symbol, name=f"{symbol} Ltd", exchange="NSE", is_active=True)
    db_session.add(stock)
    db_session.commit()
    return stock


def test_run_scan_creates_buy_signals_for_the_active_universe(
    db_session: Session, patched_session_local
) -> None:
    dates = _dates(4)
    bars = _bars(dates, [10, 10, 10, 12], [100, 100, 100, 200])
    provider = FakeMarketDataProvider(daily_prices=bars)
    _seed_buy_eligible_stock(db_session)

    summary = scan_service.run_scan(
        db_session,
        provider,
        session_date=dates[-1],
        config=_CONFIG,
        trigger="manual",
        max_concurrent_symbols=2,
        max_retries=1,
        backoff_seconds=0,
        max_notifications=10,
    )

    assert summary.status == "success"
    assert summary.universe_size == 1
    assert summary.buy_signals == 1
    assert summary.symbols_succeeded == 1
    assert summary.symbols_failed == 0

    run = db_session.get(ScanRun, summary.scan_run_id)
    assert run is not None
    assert run.status == "success"
    assert run.buy_signals == 1

    events = db_session.scalars(select(SignalEvent)).all()
    assert len(events) == 1
    assert events[0].signal_type == "BUY"
    assert events[0].scan_run_id == summary.scan_run_id


def test_run_scan_on_empty_universe_is_marked_failed(
    db_session: Session, patched_session_local
) -> None:
    provider = FakeMarketDataProvider(daily_prices=[])
    summary = scan_service.run_scan(
        db_session,
        provider,
        session_date=date(2024, 1, 10),
        config=_CONFIG,
        max_retries=1,
        backoff_seconds=0,
    )
    assert summary.status == "failed"
    assert summary.universe_size == 0
    assert "empty" in summary.error_message.lower()


def test_run_scan_raises_when_lock_already_held(
    db_session: Session, patched_session_local
) -> None:
    provider = FakeMarketDataProvider(daily_prices=[])
    handle = scan_lock_service.try_acquire(db_session)
    try:
        with pytest.raises(scan_lock_service.ScanLockHeldError):
            scan_service.run_scan(
                db_session, provider, session_date=date(2024, 1, 10), config=_CONFIG
            )
    finally:
        scan_lock_service.release(db_session, handle)


def test_run_scan_releases_lock_even_on_unexpected_error(
    db_session: Session, patched_session_local, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeMarketDataProvider(daily_prices=[])

    def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(scan_service.universe_service, "active_universe", _boom)

    with pytest.raises(RuntimeError):
        scan_service.run_scan(db_session, provider, session_date=date(2024, 1, 10), config=_CONFIG)

    # Lock must not be left held after the failure.
    assert db_session.get(ScanLock, scan_lock_service.DEFAULT_LOCK_NAME) is None
    run = db_session.scalar(select(ScanRun).order_by(ScanRun.id.desc()))
    assert run.status == "failed"


def test_run_scan_dispatches_telegram_notifications_for_new_signals(
    db_session: Session, patched_session_local, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _dates(4)
    bars = _bars(dates, [10, 10, 10, 12], [100, 100, 100, 200])
    provider = FakeMarketDataProvider(daily_prices=bars)
    _seed_buy_eligible_stock(db_session)

    monkeypatch.setattr(
        scan_service.notification_service.telegram_service,
        "send_message",
        lambda *a, **k: TelegramSendResult(success=True, status_code=200, error=None),
    )

    summary = scan_service.run_scan(
        db_session,
        provider,
        session_date=dates[-1],
        config=_CONFIG,
        max_retries=1,
        backoff_seconds=0,
        max_notifications=10,
    )

    assert summary.notifications_sent == 1
    assert summary.notifications_failed == 0
    event = db_session.scalar(select(SignalEvent))
    assert event.notification_status == "sent"


def test_run_scan_respects_max_notifications_cap(
    db_session: Session, patched_session_local, monkeypatch: pytest.MonkeyPatch
) -> None:
    dates = _dates(4)
    bars = _bars(dates, [10, 10, 10, 12], [100, 100, 100, 200])

    for symbol in ("AAA.NS", "BBB.NS", "CCC.NS"):
        _seed_buy_eligible_stock(db_session, symbol)

    provider = FakeMarketDataProvider(daily_prices=bars)
    sent_count = {"n": 0}

    def _fake_send(*args, **kwargs):
        sent_count["n"] += 1
        return TelegramSendResult(success=True, status_code=200, error=None)

    monkeypatch.setattr(
        scan_service.notification_service.telegram_service, "send_message", _fake_send
    )

    # max_concurrent_symbols=1: the test DB is a single shared in-memory
    # SQLite connection (StaticPool) - concurrent *writes* from multiple
    # worker threads on that one connection are a SQLite/test-harness
    # limitation, not something this test is trying to exercise (that's
    # covered by production using a real Postgres connection pool, one
    # connection per worker). This test is about the notification cap,
    # so it stays single-threaded to stay deterministic.
    summary = scan_service.run_scan(
        db_session,
        provider,
        session_date=dates[-1],
        config=_CONFIG,
        max_concurrent_symbols=1,
        max_retries=1,
        backoff_seconds=0,
        max_notifications=2,
    )

    assert summary.buy_signals == 3
    assert summary.notifications_sent == 2
    assert summary.notifications_skipped_cap == 1
    assert sent_count["n"] == 2


def test_rerunning_same_session_does_not_duplicate_signal_events(
    db_session: Session, patched_session_local
) -> None:
    dates = _dates(4)
    bars = _bars(dates, [10, 10, 10, 12], [100, 100, 100, 200])
    provider = FakeMarketDataProvider(daily_prices=bars)
    _seed_buy_eligible_stock(db_session)

    run_kwargs = dict(
        session_date=dates[-1], config=_CONFIG, max_retries=1, backoff_seconds=0
    )
    scan_service.run_scan(db_session, provider, **run_kwargs)
    second = scan_service.run_scan(db_session, provider, **run_kwargs)

    # Already in position after the first run - the second run for the
    # same session must not create a second BUY.
    assert second.buy_signals == 0
    events = db_session.scalars(select(SignalEvent)).all()
    assert len(events) == 1
