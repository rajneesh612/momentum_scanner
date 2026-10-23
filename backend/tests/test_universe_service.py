"""Tests for NIFTY 500 universe refresh/management - never hits NSE."""

from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.ingestion.nse_stock_list import StockListFetchError
from app.models.stock import Stock
from app.models.universe_membership import UniverseMembershipEvent
from app.services import universe_service


def _records(*symbols: str) -> list[dict]:
    return [
        {"symbol": s, "name": f"{s} Ltd", "sector": "Testing", "exchange": "NSE"} for s in symbols
    ]


def _patch_fetch(*symbols: str):
    return patch("app.services.universe_service.fetch_nifty500", return_value=_records(*symbols))


def test_refresh_creates_new_stocks_and_logs_added_event(db_session: Session) -> None:
    with patch(
        "app.services.universe_service.fetch_nifty500",
        return_value=_records("AAA.NS", "BBB.NS"),
    ):
        result = universe_service.refresh_universe(db_session)

    assert result.source_fetch_succeeded is True
    assert result.created == 2
    assert result.deactivated == 0

    stocks = db_session.scalars(select(Stock)).all()
    assert {s.symbol for s in stocks} == {"AAA.NS", "BBB.NS"}
    assert all(s.is_active for s in stocks)

    events = db_session.scalars(select(UniverseMembershipEvent)).all()
    assert len(events) == 2
    assert all(e.action == "added" for e in events)


def test_refresh_deactivates_symbols_dropped_from_list_but_never_deletes(
    db_session: Session,
) -> None:
    with _patch_fetch("AAA.NS", "BBB.NS"):
        universe_service.refresh_universe(db_session)

    with _patch_fetch("AAA.NS"):  # BBB.NS dropped out
        result = universe_service.refresh_universe(db_session)

    assert result.deactivated == 1

    bbb = db_session.scalar(select(Stock).where(Stock.symbol == "BBB.NS"))
    assert bbb is not None  # never deleted
    assert bbb.is_active is False

    removed_events = db_session.scalars(
        select(UniverseMembershipEvent).where(UniverseMembershipEvent.action == "removed")
    ).all()
    assert len(removed_events) == 1
    assert removed_events[0].stock_id == bbb.id


def test_refresh_reactivates_a_symbol_that_returns_to_the_list(db_session: Session) -> None:
    with _patch_fetch("AAA.NS", "BBB.NS"):
        universe_service.refresh_universe(db_session)
    with _patch_fetch("AAA.NS"):
        universe_service.refresh_universe(db_session)
    with _patch_fetch("AAA.NS", "BBB.NS"):
        universe_service.refresh_universe(db_session)

    bbb = db_session.scalar(select(Stock).where(Stock.symbol == "BBB.NS"))
    assert bbb.is_active is True


def test_refresh_fetch_failure_leaves_existing_universe_untouched(db_session: Session) -> None:
    with patch("app.services.universe_service.fetch_nifty500", return_value=_records("AAA.NS")):
        universe_service.refresh_universe(db_session)

    with patch(
        "app.services.universe_service.fetch_nifty500",
        side_effect=StockListFetchError("NSE unreachable"),
    ):
        result = universe_service.refresh_universe(db_session)

    assert result.source_fetch_succeeded is False
    assert result.error == "NSE unreachable"

    # Still exactly the stock from the first successful refresh - no
    # empty/partial replacement happened.
    stocks = db_session.scalars(select(Stock)).all()
    assert [s.symbol for s in stocks] == ["AAA.NS"]
    assert stocks[0].is_active is True


def test_refresh_reports_invalid_and_duplicate_records_without_dropping_silently(
    db_session: Session,
) -> None:
    bad_records = [
        {"symbol": "AAA.NS", "name": "AAA Ltd", "sector": None, "exchange": "NSE"},
        {"symbol": "", "name": "Missing Symbol", "sector": None, "exchange": "NSE"},
        {"symbol": "AAA.NS", "name": "Duplicate of AAA", "sector": None, "exchange": "NSE"},
    ]
    with patch("app.services.universe_service.fetch_nifty500", return_value=bad_records):
        result = universe_service.refresh_universe(db_session)

    assert result.created == 1
    assert len(result.invalid_records) == 1
    assert result.duplicate_symbols == ["AAA.NS"]


def test_active_universe_excludes_inactive_stocks(db_session: Session) -> None:
    with _patch_fetch("AAA.NS", "BBB.NS"):
        universe_service.refresh_universe(db_session)
    with _patch_fetch("AAA.NS"):
        universe_service.refresh_universe(db_session)

    active = universe_service.active_universe(db_session)
    assert [s.symbol for s in active] == ["AAA.NS"]


def test_last_refresh_at_is_none_before_any_refresh(db_session: Session) -> None:
    assert universe_service.last_refresh_at(db_session) is None
