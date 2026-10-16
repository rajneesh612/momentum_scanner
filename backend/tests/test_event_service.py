"""Tests for event ingestion/dedup/listing (app/services/event_service.py)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from app.data.ingestion.news_provider import NewsProviderError, RawEvent
from app.models.stock import Stock
from app.models.stock_event import StockEvent
from app.services.event_service import StockNotFoundError, ingest_events, list_events
from tests.fakes import FakeNewsProvider


def _raw_event(
    provider_event_id: str,
    title: str = "Some headline",
    category: str = "other",
    published_at: datetime | None = None,
) -> RawEvent:
    return RawEvent(
        provider="fake_provider",
        provider_event_id=provider_event_id,
        title=title,
        category=category,
        summary=None,
        published_at=published_at or datetime(2026, 1, 15, 9, 0, tzinfo=UTC),
        source_name="Test Wire",
        source_url=f"https://example.com/{provider_event_id}",
    )


def _seed_stock(db_session: Session, symbol: str = "RELIANCE.NS") -> Stock:
    stock = Stock(symbol=symbol, name=symbol, exchange="NSE")
    db_session.add(stock)
    db_session.commit()
    return stock


def test_ingest_events_creates_new_rows(db_session: Session) -> None:
    _seed_stock(db_session)
    provider = FakeNewsProvider(events=[_raw_event("e1"), _raw_event("e2")])

    result = ingest_events(db_session, provider, "RELIANCE.NS")

    assert result.created == 2
    assert result.skipped == 0
    assert db_session.query(StockEvent).count() == 2


def test_ingest_events_is_idempotent_on_repeat_ingestion(db_session: Session) -> None:
    _seed_stock(db_session)
    provider = FakeNewsProvider(events=[_raw_event("e1")])

    ingest_events(db_session, provider, "RELIANCE.NS")
    result = ingest_events(db_session, provider, "RELIANCE.NS")

    assert result.created == 0
    assert result.skipped == 1
    assert db_session.query(StockEvent).count() == 1


def test_ingest_events_raises_for_unknown_stock(db_session: Session) -> None:
    provider = FakeNewsProvider(events=[_raw_event("e1")])

    with pytest.raises(StockNotFoundError):
        ingest_events(db_session, provider, "UNKNOWN.NS")


def test_ingest_events_propagates_provider_errors(db_session: Session) -> None:
    _seed_stock(db_session)
    provider = FakeNewsProvider(raise_error=NewsProviderError("rate limited"))

    with pytest.raises(NewsProviderError):
        ingest_events(db_session, provider, "RELIANCE.NS")


def test_ingested_event_preserves_published_at_value(db_session: Session) -> None:
    # The DateTime(timezone=True) column is tz-aware in Postgres; SQLite
    # (used here) doesn't round-trip tzinfo, so compare the UTC value
    # itself rather than asserting on tzinfo presence.
    _seed_stock(db_session)
    published = datetime(2026, 3, 1, 23, 45, tzinfo=UTC)
    provider = FakeNewsProvider(events=[_raw_event("e1", published_at=published)])

    ingest_events(db_session, provider, "RELIANCE.NS")

    stored = db_session.query(StockEvent).one()
    stored_utc = stored.published_at
    if stored_utc.tzinfo is None:
        stored_utc = stored_utc.replace(tzinfo=UTC)
    assert stored_utc == published


def test_list_events_filters_by_date_range(db_session: Session) -> None:
    _seed_stock(db_session)
    provider = FakeNewsProvider(
        events=[
            _raw_event("e1", published_at=datetime(2026, 1, 1, tzinfo=UTC)),
            _raw_event("e2", published_at=datetime(2026, 2, 1, tzinfo=UTC)),
            _raw_event("e3", published_at=datetime(2026, 3, 1, tzinfo=UTC)),
        ]
    )
    ingest_events(db_session, provider, "RELIANCE.NS")

    _, events = list_events(
        db_session, "RELIANCE.NS", start_date=date(2026, 1, 15), end_date=date(2026, 2, 15)
    )

    assert [e.provider_event_id for e in events] == ["e2"]


def test_list_events_filters_by_category(db_session: Session) -> None:
    _seed_stock(db_session)
    provider = FakeNewsProvider(
        events=[
            _raw_event("e1", category="earnings"),
            _raw_event("e2", category="dividend"),
        ]
    )
    ingest_events(db_session, provider, "RELIANCE.NS")

    _, events = list_events(db_session, "RELIANCE.NS", category="dividend")

    assert [e.provider_event_id for e in events] == ["e2"]


def test_list_events_sorted_by_published_at(db_session: Session) -> None:
    _seed_stock(db_session)
    provider = FakeNewsProvider(
        events=[
            _raw_event("later", published_at=datetime(2026, 2, 1, tzinfo=UTC)),
            _raw_event("earlier", published_at=datetime(2026, 1, 1, tzinfo=UTC)),
        ]
    )
    ingest_events(db_session, provider, "RELIANCE.NS")

    _, events = list_events(db_session, "RELIANCE.NS")

    assert [e.provider_event_id for e in events] == ["earlier", "later"]


def test_events_never_cross_associate_between_stocks(db_session: Session) -> None:
    _seed_stock(db_session, "RELIANCE.NS")
    _seed_stock(db_session, "TCS.NS")
    ingest_events(db_session, FakeNewsProvider(events=[_raw_event("e1")]), "RELIANCE.NS")

    _, tcs_events = list_events(db_session, "TCS.NS")

    assert tcs_events == []
