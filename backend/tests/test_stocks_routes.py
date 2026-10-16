"""Tests for GET /api/v1/stocks/{symbol}/history."""

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.price_history import PriceHistory
from app.models.stock import Stock


def _seed_stock_with_prices(db_session: Session) -> None:
    stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries", exchange="NSE")
    db_session.add(stock)
    db_session.flush()
    db_session.add(
        PriceHistory(
            stock_id=stock.id,
            date=date(2024, 1, 2),
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            adjusted_close=103.5,
            volume=1_000_000,
        )
    )
    db_session.commit()


def test_get_history_returns_normalized_prices(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session)

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/history",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["exchange"] == "NSE"
    assert body["count"] == 1
    assert body["prices"] == [
        {
            "date": "2024-01-02",
            "interval": "1d",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "adjusted_close": 103.5,
            "volume": 1_000_000,
        }
    ]


def test_get_history_returns_404_for_unknown_symbol(db_client: TestClient) -> None:
    response = db_client.get(
        "/api/v1/stocks/UNKNOWN.NS/history",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
    )

    assert response.status_code == 404


def test_get_history_returns_404_when_no_data_in_range(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session)

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/history",
        params={"start_date": "2025-01-01", "end_date": "2025-01-31"},
    )

    assert response.status_code == 404


def test_get_history_rejects_invalid_date_range(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session)

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/history",
        params={"start_date": "2024-02-01", "end_date": "2024-01-01"},
    )

    assert response.status_code == 400


def test_get_history_requires_date_query_params(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks/RELIANCE.NS/history")

    assert response.status_code == 422


def test_get_history_rejects_invalid_interval(db_client: TestClient, db_session: Session) -> None:
    _seed_stock_with_prices(db_session)

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/history",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31", "interval": "5min"},
    )

    assert response.status_code == 400


def test_get_history_filters_by_interval(db_client: TestClient, db_session: Session) -> None:
    _seed_stock_with_prices(db_session)

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/history",
        params={"start_date": "2024-01-01", "end_date": "2024-01-31", "interval": "1wk"},
    )

    assert response.status_code == 404
