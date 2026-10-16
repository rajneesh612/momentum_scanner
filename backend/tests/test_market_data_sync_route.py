"""Tests for POST /api/v1/market-data/sync/{symbol}.

The market-data provider is always overridden with FakeMarketDataProvider
here — no real Yahoo Finance network calls are made.
"""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_provider
from app.data.ingestion.provider import (
    MarketDataProviderError,
    NoDataFoundError,
    SymbolNotFoundError,
)
from app.main import app
from app.models.price_history import PriceHistory
from app.models.stock import Stock
from tests.fakes import FakeMarketDataProvider


def _override_provider(provider: FakeMarketDataProvider) -> None:
    app.dependency_overrides[get_market_data_provider] = lambda: provider


def test_sync_success_persists_price_history(db_client: TestClient, db_session: Session) -> None:
    _override_provider(
        FakeMarketDataProvider(
            daily_prices=[
                {
                    "date": date(2024, 1, 2),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                    "adjusted_close": 103.5,
                    "volume": 1_000_000,
                }
            ]
        )
    )

    response = db_client.post(
        "/api/v1/market-data/sync/RELIANCE.NS",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["records_created"] == 1
    assert body["records_fetched"] == 1

    stock = db_session.query(Stock).filter_by(symbol="RELIANCE.NS").one()
    assert db_session.query(PriceHistory).filter_by(stock_id=stock.id).count() == 1


def test_sync_returns_404_for_symbol_not_found(db_client: TestClient) -> None:
    _override_provider(FakeMarketDataProvider(raise_error=SymbolNotFoundError("nope")))

    response = db_client.post("/api/v1/market-data/sync/BADSYMBOL")

    assert response.status_code == 404


def test_sync_returns_404_for_no_data_found(db_client: TestClient) -> None:
    _override_provider(FakeMarketDataProvider(raise_error=NoDataFoundError("no data")))

    response = db_client.post("/api/v1/market-data/sync/RELIANCE.NS")

    assert response.status_code == 404


def test_sync_returns_502_for_provider_failure(db_client: TestClient) -> None:
    _override_provider(FakeMarketDataProvider(raise_error=MarketDataProviderError("boom")))

    response = db_client.post("/api/v1/market-data/sync/RELIANCE.NS")

    assert response.status_code == 502


def test_sync_rejects_invalid_date_range(db_client: TestClient) -> None:
    _override_provider(FakeMarketDataProvider())

    response = db_client.post(
        "/api/v1/market-data/sync/RELIANCE.NS",
        params={"start_date": "2024-02-01", "end_date": "2024-01-01"},
    )

    assert response.status_code == 400


def test_sync_rejects_invalid_interval(db_client: TestClient) -> None:
    _override_provider(FakeMarketDataProvider())

    response = db_client.post(
        "/api/v1/market-data/sync/RELIANCE.NS",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31", "interval": "5min"},
    )

    assert response.status_code == 400


def test_sync_accepts_weekly_interval(db_client: TestClient, db_session: Session) -> None:
    _override_provider(
        FakeMarketDataProvider(
            daily_prices=[
                {
                    "date": date(2024, 1, 1),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                    "adjusted_close": 103.5,
                    "volume": 1_000_000,
                }
            ]
        )
    )

    response = db_client.post(
        "/api/v1/market-data/sync/RELIANCE.NS",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31", "interval": "1wk"},
    )

    assert response.status_code == 200
    assert response.json()["interval"] == "1wk"

    stock = db_session.query(Stock).filter_by(symbol="RELIANCE.NS").one()
    row = db_session.query(PriceHistory).filter_by(stock_id=stock.id).one()
    assert row.interval == "1wk"
