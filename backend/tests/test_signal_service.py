"""Tests for per-symbol hybrid-signal evaluation and persistence."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.ingestion.provider import MarketDataProviderError
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.momentum.hybrid_signal import HybridStrategyConfig
from app.services.market_data_service import MarketDataService
from app.services.signal_service import scan_symbol
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


def _bars(dates: list[date], closes: list[float], volumes: list[float]) -> list[dict]:
    return [
        {
            "date": d,
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "adjusted_close": c,
            "volume": v,
        }
        for d, c, v in zip(dates, closes, volumes, strict=True)
    ]


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_scan_symbol_creates_a_buy_signal_event(db_session: Session) -> None:
    dates = _dates(4)
    bars = _bars(dates, [10, 10, 10, 12], [100, 100, 100, 200])
    provider = FakeMarketDataProvider(daily_prices=bars)
    service = MarketDataService(provider)
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE")
    db_session.add(stock)
    db_session.commit()

    outcome = scan_symbol(db_session, service, stock, _CONFIG, dates[-1], scan_run_id=None)

    assert outcome.status == "signal"
    assert outcome.signal_type == "BUY"

    events = db_session.scalars(select(SignalEvent)).all()
    assert len(events) == 1
    assert events[0].signal_type == "BUY"
    assert events[0].session_date == dates[-1]
    assert events[0].notification_status == "pending"


def test_scan_symbol_does_not_repeat_buy_while_already_in_position(db_session: Session) -> None:
    dates = _dates(5)
    bars = _bars(dates, [10, 10, 10, 12, 14], [100, 100, 100, 200, 100])
    provider = FakeMarketDataProvider(daily_prices=bars)
    service = MarketDataService(provider)
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE")
    db_session.add(stock)
    db_session.commit()

    scan_symbol(db_session, service, stock, _CONFIG, dates[3], scan_run_id=None)  # BUY
    # Still eligible/up the next day - must not re-trigger a second BUY.
    outcome = scan_symbol(db_session, service, stock, _CONFIG, dates[4], scan_run_id=None)

    assert outcome.status == "ok_no_signal"
    events = db_session.scalars(select(SignalEvent)).all()
    assert len(events) == 1  # no second BUY recorded


def test_scan_symbol_reports_missing_when_no_data_at_all(db_session: Session) -> None:
    provider = FakeMarketDataProvider(daily_prices=[])
    service = MarketDataService(provider)
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE")
    db_session.add(stock)
    db_session.commit()

    outcome = scan_symbol(db_session, service, stock, _CONFIG, date(2024, 1, 10), scan_run_id=None)

    assert outcome.status == "missing"
    assert db_session.scalars(select(SignalEvent)).all() == []


def test_scan_symbol_survives_provider_errors_and_uses_whatever_is_stored(
    db_session: Session,
) -> None:
    dates = _dates(4)
    bars = _bars(dates, [10, 10, 10, 12], [100, 100, 100, 200])
    provider = FakeMarketDataProvider(daily_prices=bars)
    service = MarketDataService(provider)
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE")
    db_session.add(stock)
    db_session.commit()

    # Prime stored history via a normal sync, then switch the provider to
    # one that always errors - the opportunistic top-up must fail
    # silently and the scan must still use the already-stored data.
    service.sync_symbol_history(db_session, "AAA.NS", dates[0], dates[-1], "1d")
    failing_provider = FakeMarketDataProvider(raise_error=MarketDataProviderError("network down"))
    failing_service = MarketDataService(failing_provider)

    outcome = scan_symbol(
        db_session,
        failing_service,
        stock,
        _CONFIG,
        dates[-1],
        scan_run_id=None,
        max_retries=1,
        backoff_seconds=0,
    )

    assert outcome.status == "signal"
    assert outcome.signal_type == "BUY"
