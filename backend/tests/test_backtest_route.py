"""Tests for POST /api/v1/backtest/{symbol}."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_provider
from app.data.ingestion.provider import MarketDataProviderError
from app.main import app
from app.models.price_history import PriceHistory
from app.models.stock import Stock
from tests.fakes import FakeMarketDataProvider


@pytest.fixture(autouse=True)
def _stub_market_data_provider():
    """The backtest route now opportunistically tops up missing history
    via the provider before reading — stub it for every test in this
    file so none of them ever make a real Yahoo Finance call. An empty
    fake is a harmless no-op against the directly-seeded PriceHistory
    rows these tests already rely on.
    """
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketDataProvider(
        daily_prices=[]
    )
    yield


def _seed_stock_with_prices(db_session: Session, closes: list[float]) -> None:
    stock = Stock(symbol="RELIANCE.NS", name="Reliance Industries", exchange="NSE")
    db_session.add(stock)
    db_session.flush()

    start = date(2024, 1, 1)
    for i, close in enumerate(closes):
        db_session.add(
            PriceHistory(
                stock_id=stock.id,
                date=start + timedelta(days=i),
                open=close,
                high=close,
                low=close,
                close=close,
                adjusted_close=close,
                volume=1_000_000,
            )
        )
    db_session.commit()


def test_backtest_returns_summary_equity_curve_and_trades(
    db_client: TestClient, db_session: Session
) -> None:
    closes = [10, 10, 12, 14, 11, 9, 13, 15]
    _seed_stock_with_prices(db_session, closes)

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-08",
            "short_window": 1,
            "long_window": 2,
            "initial_capital": 1000,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "RELIANCE.NS"
    assert body["strategy"] == "sma_crossover"
    assert body["short_window"] == 1
    assert body["long_window"] == 2
    assert len(body["equity_curve"]) == 8
    assert len(body["trades"]) == 2
    assert body["trades"][0]["is_open"] is False
    assert body["trades"][1]["is_open"] is True
    assert body["summary"]["num_trades"] == 1
    assert body["summary"]["initial_capital"] == 1000
    assert body["equity_curve"][0]["short_sma"] == pytest.approx(10)
    assert body["equity_curve"][0]["long_sma"] is None
    assert body["equity_curve"][1]["long_sma"] == pytest.approx(10)


def test_backtest_returns_404_for_unknown_symbol(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/backtest/UNKNOWN.NS",
        params={"start_date": "2024-01-01", "end_date": "2024-01-08"},
    )

    assert response.status_code == 404


def test_backtest_returns_404_when_no_data_in_window(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12])

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={"start_date": "2025-01-01", "end_date": "2025-01-31"},
    )

    assert response.status_code == 404


def test_backtest_rejects_invalid_date_range(db_client: TestClient, db_session: Session) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12])

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={"start_date": "2024-02-01", "end_date": "2024-01-01"},
    )

    assert response.status_code == 400


def test_backtest_rejects_short_window_not_less_than_long_window(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12])

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "short_window": 50,
            "long_window": 20,
        },
    )

    assert response.status_code == 400


def test_backtest_rejects_invalid_interval(db_client: TestClient, db_session: Session) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12])

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={"start_date": "2024-01-01", "end_date": "2024-01-03", "interval": "5min"},
    )

    assert response.status_code == 400


def test_backtest_rejects_non_positive_initial_capital(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12])

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "initial_capital": 0,
        },
    )

    assert response.status_code == 400


def test_backtest_reports_warmup_fields(db_client: TestClient, db_session: Session) -> None:
    closes = [10, 10, 12, 14, 11, 9, 13, 15]
    _seed_stock_with_prices(db_session, closes)  # dates 2024-01-01..01-08

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-08",
            "short_window": 1,
            "long_window": 2,
        },
    )

    body = response.json()
    assert body["warmup_complete_date"] == "2024-01-02"
    assert body["is_fully_warmed_up"] is False


def test_backtest_is_fully_warmed_up_when_lookback_covers_long_window(
    db_client: TestClient, db_session: Session
) -> None:
    # 10 days total; backtest only the last 5 - long_window=2 needs just 1
    # prior bar, easily covered by the 5 lookback days available.
    closes = [10, 10, 11, 12, 13, 14, 15, 16, 17, 18]
    _seed_stock_with_prices(db_session, closes)  # dates 2024-01-01..01-10

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-06",
            "end_date": "2024-01-10",
            "short_window": 1,
            "long_window": 2,
        },
    )

    body = response.json()
    assert body["is_fully_warmed_up"] is True
    assert body["warmup_complete_date"] == "2024-01-06"
    assert body["lookback_bars"] == 5


def test_backtest_distinguishes_insufficient_data_from_zero_trades(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12])  # only 3 days exist anywhere

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "short_window": 1,
            "long_window": 200,
        },
    )

    body = response.json()
    assert body["summary"]["num_trades"] == 0
    assert body["is_fully_warmed_up"] is False


def test_backtest_zero_trades_when_fully_warmed_and_flat(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session, [10.0] * 8)  # flat price, 2024-01-01..01-08

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-03",
            "end_date": "2024-01-08",
            "short_window": 1,
            "long_window": 2,
        },
    )

    body = response.json()
    assert body["summary"]["num_trades"] == 0
    assert body["is_fully_warmed_up"] is True
    assert body["lookback_bars"] == 2


def test_backtest_equity_curve_starts_at_initial_capital_even_with_day_one_trade(
    db_client: TestClient, db_session: Session
) -> None:
    closes = [5, 10, 9]  # day0 lookback, buy@10 on window day 1
    _seed_stock_with_prices(db_session, closes)  # dates 2024-01-01..01-03

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-02",
            "end_date": "2024-01-03",
            "short_window": 1,
            "long_window": 2,
            "initial_capital": 50000,
        },
    )

    body = response.json()
    assert body["equity_curve"][0]["in_position"] is True
    assert body["equity_curve"][0]["equity"] == pytest.approx(50000)
    assert body["summary"]["initial_capital"] == 50000


def test_backtest_tops_up_missing_lookback_via_provider(
    db_client: TestClient, db_session: Session
) -> None:
    window_closes = [10, 10, 12, 14, 11, 9]
    _seed_stock_with_prices(db_session, window_closes)  # 2024-01-01..01-06 only

    stock = db_session.query(Stock).filter_by(symbol="RELIANCE.NS").one()
    assert db_session.query(PriceHistory).filter_by(stock_id=stock.id).count() == 6

    # Pretend Yahoo Finance actually has 2 extra days before the window too.
    full_closes = [8, 9, *window_closes]
    full_records = [
        {
            "date": date(2023, 12, 30) + timedelta(days=i),
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "adjusted_close": c,
            "volume": 1000,
        }
        for i, c in enumerate(full_closes)
    ]
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketDataProvider(
        daily_prices=full_records
    )

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-06",
            "short_window": 1,
            "long_window": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["lookback_bars"] == 2
    assert db_session.query(PriceHistory).filter_by(stock_id=stock.id).count() == 8


def test_backtest_resilient_to_provider_failure_during_topup(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock_with_prices(db_session, [10, 11, 12, 13, 14, 15])

    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketDataProvider(
        raise_error=MarketDataProviderError("rate limited")
    )

    response = db_client.post(
        "/api/v1/backtest/RELIANCE.NS",
        params={
            "start_date": "2024-01-01",
            "end_date": "2024-01-06",
            "short_window": 1,
            "long_window": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["lookback_bars"] == 0
