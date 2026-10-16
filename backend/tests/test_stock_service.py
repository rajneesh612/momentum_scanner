"""Tests for the stock master import/list service."""

from typing import Any

from sqlalchemy.orm import Session

from app.models.stock import Stock
from app.services.stock_service import import_stocks, list_stocks


def _record(symbol: str, name: str, sector: str = "IT") -> dict[str, Any]:
    return {"symbol": symbol, "name": name, "sector": sector, "exchange": "NSE"}


def test_import_stocks_creates_new_rows(db_session: Session) -> None:
    result = import_stocks(
        db_session,
        [
            _record("TCS.NS", "Tata Consultancy Services Ltd."),
            _record("INFY.NS", "Infosys Ltd."),
        ],
    )

    assert result.created == 2
    assert result.updated == 0
    assert db_session.query(Stock).count() == 2


def test_import_stocks_is_idempotent_on_repeat_import(db_session: Session) -> None:
    records = [_record("TCS.NS", "Tata Consultancy Services Ltd.")]
    import_stocks(db_session, records)
    result = import_stocks(db_session, records)

    assert result.created == 0
    assert result.updated == 0
    assert result.unchanged == 1
    assert db_session.query(Stock).filter_by(symbol="TCS.NS").count() == 1


def test_import_stocks_updates_changed_fields_without_duplicating(db_session: Session) -> None:
    import_stocks(db_session, [_record("TCS.NS", "Tata Consultancy Services Ltd.", sector="IT")])
    result = import_stocks(
        db_session, [_record("TCS.NS", "TCS Ltd. (renamed)", sector="Technology")]
    )

    assert result.updated == 1
    assert result.created == 0
    assert db_session.query(Stock).filter_by(symbol="TCS.NS").count() == 1
    stock = db_session.query(Stock).filter_by(symbol="TCS.NS").one()
    assert stock.name == "TCS Ltd. (renamed)"
    assert stock.sector == "Technology"


def test_import_stocks_defaults_new_rows_active(db_session: Session) -> None:
    import_stocks(db_session, [_record("TCS.NS", "Tata Consultancy Services Ltd.")])

    stock = db_session.query(Stock).filter_by(symbol="TCS.NS").one()
    assert stock.is_active is True


def test_list_stocks_searches_by_name(db_session: Session) -> None:
    import_stocks(
        db_session,
        [
            _record("TCS.NS", "Tata Consultancy Services Ltd."),
            _record("RELIANCE.NS", "Reliance Industries Ltd."),
        ],
    )

    items, total = list_stocks(db_session, q="tata")

    assert total == 1
    assert items[0].symbol == "TCS.NS"


def test_list_stocks_searches_by_symbol(db_session: Session) -> None:
    import_stocks(
        db_session,
        [
            _record("TCS.NS", "Tata Consultancy Services Ltd."),
            _record("RELIANCE.NS", "Reliance Industries Ltd."),
        ],
    )

    items, total = list_stocks(db_session, q="relia")

    assert total == 1
    assert items[0].symbol == "RELIANCE.NS"


def test_list_stocks_filters_active_by_default(db_session: Session) -> None:
    import_stocks(db_session, [_record("TCS.NS", "Tata Consultancy Services Ltd.")])
    stock = db_session.query(Stock).filter_by(symbol="TCS.NS").one()
    stock.is_active = False
    db_session.commit()

    _, total_active = list_stocks(db_session)
    assert total_active == 0

    _, total_all = list_stocks(db_session, is_active=None)
    assert total_all == 1


def test_list_stocks_paginates_with_stable_sort(db_session: Session) -> None:
    import_stocks(
        db_session,
        [
            _record("ZZZ.NS", "Zed Corp"),
            _record("AAA.NS", "Aaa Corp"),
            _record("MMM.NS", "Mmm Corp"),
        ],
    )

    page1, total = list_stocks(db_session, limit=2, offset=0)
    page2, _ = list_stocks(db_session, limit=2, offset=2)

    assert total == 3
    assert [s.symbol for s in page1] == ["AAA.NS", "MMM.NS"]
    assert [s.symbol for s in page2] == ["ZZZ.NS"]


def test_list_stocks_empty_results(db_session: Session) -> None:
    items, total = list_stocks(db_session, q="nonexistent")

    assert items == []
    assert total == 0
