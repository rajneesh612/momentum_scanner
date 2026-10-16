"""Unit tests for MarketDataService."""

from datetime import date
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.price_history import PriceHistory
from app.models.stock import Stock
from app.services.market_data_service import (
    MarketDataPersistenceError,
    MarketDataService,
    StockNotFoundError,
)
from tests.fakes import FakeMarketDataProvider


def _price_record(day: date, close: float = 100.0) -> dict[str, Any]:
    return {
        "date": day,
        "open": close,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "adjusted_close": close,
        "volume": 1000,
    }


def test_sync_symbol_history_creates_stock_and_prices(db_session: Session) -> None:
    provider = FakeMarketDataProvider(
        daily_prices=[_price_record(date(2024, 1, 2)), _price_record(date(2024, 1, 3))]
    )
    service = MarketDataService(provider)

    result = service.sync_symbol_history(
        db_session, "reliance.ns", date(2024, 1, 1), date(2024, 1, 5)
    )

    assert result.records_fetched == 2
    assert result.records_created == 2
    assert result.records_skipped == 0

    stock = db_session.query(Stock).filter_by(symbol="RELIANCE.NS").one()
    assert stock.exchange == "NSE"
    assert db_session.query(PriceHistory).filter_by(stock_id=stock.id).count() == 2


def test_sync_symbol_history_skips_existing_duplicate_dates(db_session: Session) -> None:
    provider = FakeMarketDataProvider(daily_prices=[_price_record(date(2024, 1, 2))])
    service = MarketDataService(provider)

    service.sync_symbol_history(db_session, "TCS.NS", date(2024, 1, 1), date(2024, 1, 5))
    result = service.sync_symbol_history(db_session, "TCS.NS", date(2024, 1, 1), date(2024, 1, 5))

    assert result.records_created == 0
    assert result.records_skipped == 1

    stock = db_session.query(Stock).filter_by(symbol="TCS.NS").one()
    assert db_session.query(PriceHistory).filter_by(stock_id=stock.id).count() == 1


def test_sync_symbol_history_raises_persistence_error_on_commit_failure(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FakeMarketDataProvider(daily_prices=[_price_record(date(2024, 1, 2))])
    service = MarketDataService(provider)

    def _raise_on_commit() -> None:
        raise SQLAlchemyError("connection lost")

    monkeypatch.setattr(db_session, "commit", _raise_on_commit)

    with pytest.raises(MarketDataPersistenceError):
        service.sync_symbol_history(db_session, "HDFC.NS", date(2024, 1, 1), date(2024, 1, 5))


def test_get_price_history_raises_when_stock_missing(db_session: Session) -> None:
    service = MarketDataService(FakeMarketDataProvider())

    with pytest.raises(StockNotFoundError):
        service.get_price_history(db_session, "UNKNOWN.NS", date(2024, 1, 1), date(2024, 1, 5))


def test_sync_symbol_history_keeps_daily_and_weekly_bars_separate(db_session: Session) -> None:
    provider = FakeMarketDataProvider(daily_prices=[_price_record(date(2024, 1, 2))])
    service = MarketDataService(provider)

    service.sync_symbol_history(db_session, "TCS.NS", date(2024, 1, 1), date(2024, 1, 5), "1d")
    result = service.sync_symbol_history(
        db_session, "TCS.NS", date(2024, 1, 1), date(2024, 1, 5), "1wk"
    )

    assert result.records_created == 1

    stock = db_session.query(Stock).filter_by(symbol="TCS.NS").one()
    assert db_session.query(PriceHistory).filter_by(stock_id=stock.id).count() == 2
    intervals = {
        row.interval for row in db_session.query(PriceHistory).filter_by(stock_id=stock.id).all()
    }
    assert intervals == {"1d", "1wk"}


def test_get_price_history_filters_by_interval(db_session: Session) -> None:
    stock = Stock(symbol="TCS.NS", name="TCS.NS", exchange="NSE")
    db_session.add(stock)
    db_session.flush()
    db_session.add_all(
        [
            PriceHistory(stock_id=stock.id, interval="1d", **_price_record(date(2024, 1, 2))),
            PriceHistory(stock_id=stock.id, interval="1wk", **_price_record(date(2024, 1, 2))),
        ]
    )
    db_session.commit()

    service = MarketDataService(FakeMarketDataProvider())
    _, weekly_prices = service.get_price_history(
        db_session, "TCS.NS", date(2024, 1, 1), date(2024, 1, 5), "1wk"
    )

    assert len(weekly_prices) == 1
    assert weekly_prices[0].interval == "1wk"


def test_get_price_history_returns_rows_within_range(db_session: Session) -> None:
    stock = Stock(symbol="INFY.NS", name="INFY.NS", exchange="NSE")
    db_session.add(stock)
    db_session.flush()
    db_session.add_all(
        [
            PriceHistory(stock_id=stock.id, **_price_record(date(2024, 1, 2))),
            PriceHistory(stock_id=stock.id, **_price_record(date(2024, 6, 1))),
        ]
    )
    db_session.commit()

    service = MarketDataService(FakeMarketDataProvider())
    _, prices = service.get_price_history(
        db_session, "INFY.NS", date(2024, 1, 1), date(2024, 2, 1)
    )

    assert len(prices) == 1
    assert prices[0].date == date(2024, 1, 2)
