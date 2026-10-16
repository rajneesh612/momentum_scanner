"""Tests for GET /api/v1/stocks/{symbol}/events and .../events/{id}/impact."""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_provider, get_news_provider
from app.data.ingestion.news_provider import NewsProviderError, RawEvent
from app.main import app
from app.models.price_history import PriceHistory
from app.models.stock import Stock
from app.models.stock_event import StockEvent
from tests.fakes import FakeMarketDataProvider, FakeNewsProvider


def _raw_event(
    provider_event_id: str, published_at: datetime, category: str = "earnings"
) -> RawEvent:
    return RawEvent(
        provider="fake_provider",
        provider_event_id=provider_event_id,
        title=f"Event {provider_event_id}",
        category=category,
        summary="A short factual summary.",
        published_at=published_at,
        source_name="Test Wire",
        source_url=f"https://example.com/{provider_event_id}",
    )


def _stub_news(events=None, raise_error=None) -> None:
    app.dependency_overrides[get_news_provider] = lambda: FakeNewsProvider(
        events=events or [], raise_error=raise_error
    )


def _stub_market_data(daily_prices=None, raise_error=None) -> None:
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketDataProvider(
        daily_prices=daily_prices or [], raise_error=raise_error
    )


def _seed_stock(db_session: Session, symbol: str = "RELIANCE.NS") -> Stock:
    stock = Stock(symbol=symbol, name=symbol, exchange="NSE")
    db_session.add(stock)
    db_session.commit()
    return stock


def _seed_prices(db_session: Session, stock: Stock, start: date, closes: list[float]) -> None:
    for i, close in enumerate(closes):
        db_session.add(
            PriceHistory(
                stock_id=stock.id,
                date=start + timedelta(days=i),
                interval="1d",
                open=close,
                high=close,
                low=close,
                close=close,
                adjusted_close=close,
                volume=1_000_000,
            )
        )
    db_session.commit()


# ---- GET /stocks/{symbol}/events ----


def test_list_events_returns_ingested_from_provider(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock(db_session)
    _stub_news(events=[_raw_event("e1", datetime(2026, 1, 1, tzinfo=UTC))])

    response = db_client.get("/api/v1/stocks/RELIANCE.NS/events")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["news_unavailable"] is False
    assert body["events"][0]["title"] == "Event e1"


def test_list_events_filters_by_date_range(db_client: TestClient, db_session: Session) -> None:
    _seed_stock(db_session)
    _stub_news(
        events=[
            _raw_event("old", datetime(2025, 1, 1, tzinfo=UTC)),
            _raw_event("in_range", datetime(2026, 1, 15, tzinfo=UTC)),
        ]
    )

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/events",
        params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
    )

    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["title"] == "Event in_range"


def test_list_events_filters_by_category(db_client: TestClient, db_session: Session) -> None:
    _seed_stock(db_session)
    _stub_news(
        events=[
            _raw_event("e1", datetime(2026, 1, 1, tzinfo=UTC), category="earnings"),
            _raw_event("e2", datetime(2026, 1, 2, tzinfo=UTC), category="dividend"),
        ]
    )

    response = db_client.get("/api/v1/stocks/RELIANCE.NS/events", params={"category": "dividend"})

    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["category"] == "dividend"


def test_list_events_404_for_unknown_stock(db_client: TestClient) -> None:
    _stub_news()
    response = db_client.get("/api/v1/stocks/UNKNOWN.NS/events")
    assert response.status_code == 404


def test_list_events_rejects_invalid_date_range(db_client: TestClient, db_session: Session) -> None:
    _seed_stock(db_session)
    _stub_news()

    response = db_client.get(
        "/api/v1/stocks/RELIANCE.NS/events",
        params={"start_date": "2026-02-01", "end_date": "2026-01-01"},
    )

    assert response.status_code == 400


def test_list_events_rejects_invalid_category(db_client: TestClient, db_session: Session) -> None:
    _seed_stock(db_session)
    _stub_news()

    response = db_client.get("/api/v1/stocks/RELIANCE.NS/events", params={"category": "nonsense"})

    assert response.status_code == 400


def test_list_events_resilient_when_provider_fails_but_data_exists(
    db_client: TestClient, db_session: Session
) -> None:
    stock = _seed_stock(db_session)
    db_session.add(
        StockEvent(
            stock_id=stock.id,
            title="Already ingested",
            category="other",
            summary=None,
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_name="Test Wire",
            source_url="https://example.com/already",
            provider="fake_provider",
            provider_event_id="already",
        )
    )
    db_session.commit()
    _stub_news(raise_error=NewsProviderError("rate limited"))

    response = db_client.get("/api/v1/stocks/RELIANCE.NS/events")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["news_unavailable"] is False


def test_list_events_news_unavailable_when_nothing_exists(
    db_client: TestClient, db_session: Session
) -> None:
    _seed_stock(db_session)
    _stub_news(raise_error=NewsProviderError("rate limited"))

    response = db_client.get("/api/v1/stocks/RELIANCE.NS/events")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["news_unavailable"] is True


# ---- GET /stocks/{symbol}/events/{event_id}/impact ----


def test_event_impact_computes_ok_windows_with_benchmark(
    db_client: TestClient, db_session: Session
) -> None:
    _stub_news()
    stock = _seed_stock(db_session, "RELIANCE.NS")
    benchmark = _seed_stock(db_session, "^NSEI")
    event_start = date(2026, 1, 1)
    _seed_prices(db_session, stock, event_start, [100.0 + i for i in range(130)])
    _seed_prices(db_session, benchmark, event_start, [1000.0 + i for i in range(130)])
    _stub_market_data()  # no real sync needed, data already local

    event = StockEvent(
        stock_id=stock.id,
        title="Earnings beat",
        category="earnings",
        summary=None,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_name="Test Wire",
        source_url="https://example.com/e1",
        provider="fake_provider",
        provider_event_id="e1",
    )
    db_session.add(event)
    db_session.commit()

    response = db_client.get(f"/api/v1/stocks/RELIANCE.NS/events/{event.id}/impact")

    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_available"] is True
    assert all(w["status"] == "ok" for w in body["windows"])
    assert len(body["interpretation"]) > 0


def test_event_impact_pending_when_too_recent(db_client: TestClient, db_session: Session) -> None:
    from app.data.ingestion.provider import MarketDataProviderError

    _stub_news()
    stock = _seed_stock(db_session, "RELIANCE.NS")
    today = date.today()
    _seed_prices(db_session, stock, today, [100.0, 101.0])
    _stub_market_data(raise_error=MarketDataProviderError("no network in test"))

    event = StockEvent(
        stock_id=stock.id,
        title="Just announced",
        category="other",
        summary=None,
        published_at=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
        source_name="Test Wire",
        source_url="https://example.com/fresh",
        provider="fake_provider",
        provider_event_id="fresh",
    )
    db_session.add(event)
    db_session.commit()

    response = db_client.get(f"/api/v1/stocks/RELIANCE.NS/events/{event.id}/impact")

    assert response.status_code == 200
    body = response.json()
    long_window = next(w for w in body["windows"] if w["trading_days"] == 120)
    assert long_window["status"] == "pending"


def test_event_impact_no_benchmark_when_unavailable(
    db_client: TestClient, db_session: Session
) -> None:
    _stub_news()
    stock = _seed_stock(db_session, "RELIANCE.NS")
    event_start = date(2026, 1, 1)
    _seed_prices(db_session, stock, event_start, [100.0 + i for i in range(10)])
    # No benchmark Stock/PriceHistory seeded, and the top-up attempt fails.
    from app.data.ingestion.provider import MarketDataProviderError

    _stub_market_data(raise_error=MarketDataProviderError("no network in test"))

    event = StockEvent(
        stock_id=stock.id,
        title="Earnings beat",
        category="earnings",
        summary=None,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_name="Test Wire",
        source_url="https://example.com/e1",
        provider="fake_provider",
        provider_event_id="e1",
    )
    db_session.add(event)
    db_session.commit()

    response = db_client.get(f"/api/v1/stocks/RELIANCE.NS/events/{event.id}/impact")

    assert response.status_code == 200
    body = response.json()
    assert body["benchmark_available"] is False
    assert all(w["benchmark_return_pct"] is None for w in body["windows"])


def test_event_impact_404_for_unknown_event(db_client: TestClient, db_session: Session) -> None:
    _stub_news()
    _seed_stock(db_session, "RELIANCE.NS")
    _stub_market_data()

    response = db_client.get("/api/v1/stocks/RELIANCE.NS/events/99999/impact")

    assert response.status_code == 404


def test_event_impact_404_when_event_belongs_to_different_stock(
    db_client: TestClient, db_session: Session
) -> None:
    _stub_news()
    reliance = _seed_stock(db_session, "RELIANCE.NS")
    _seed_stock(db_session, "TCS.NS")
    _stub_market_data()

    event = StockEvent(
        stock_id=reliance.id,
        title="Reliance event",
        category="other",
        summary=None,
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_name="Test Wire",
        source_url="https://example.com/e1",
        provider="fake_provider",
        provider_event_id="e1",
    )
    db_session.add(event)
    db_session.commit()

    response = db_client.get(f"/api/v1/stocks/TCS.NS/events/{event.id}/impact")

    assert response.status_code == 404
