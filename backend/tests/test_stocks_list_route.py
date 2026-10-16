"""Tests for GET /api/v1/stocks."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.stock import Stock


def _seed(db_session: Session) -> None:
    db_session.add_all(
        [
            Stock(
                symbol="TCS.NS", name="Tata Consultancy Services Ltd.", exchange="NSE", sector="IT"
            ),
            Stock(
                symbol="RELIANCE.NS",
                name="Reliance Industries Ltd.",
                exchange="NSE",
                sector="Energy",
            ),
            Stock(
                symbol="DELISTED.NS",
                name="Delisted Corp",
                exchange="NSE",
                sector="IT",
                is_active=False,
            ),
        ]
    )
    db_session.commit()


def test_list_stocks_returns_active_by_default(db_client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["symbol"] for item in body["items"]} == {"TCS.NS", "RELIANCE.NS"}


def test_list_stocks_search_by_name(db_client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks", params={"q": "tata"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "TCS.NS"


def test_list_stocks_search_by_symbol(db_client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks", params={"q": "reliance"})

    assert response.status_code == 200
    assert response.json()["items"][0]["symbol"] == "RELIANCE.NS"


def test_list_stocks_includes_inactive_when_requested(
    db_client: TestClient, db_session: Session
) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks", params={"is_active": "false"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["symbol"] == "DELISTED.NS"


def test_list_stocks_pagination(db_client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks", params={"limit": 1, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 0


def test_list_stocks_is_stably_sorted_by_symbol(db_client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks", params={"limit": 2})

    assert response.json()["items"][0]["symbol"] == "RELIANCE.NS"
    assert response.json()["items"][1]["symbol"] == "TCS.NS"


def test_list_stocks_empty_results_returns_200(db_client: TestClient, db_session: Session) -> None:
    _seed(db_session)

    response = db_client.get("/api/v1/stocks", params={"q": "nonexistent"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_stocks_rejects_invalid_limit(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks", params={"limit": 0})

    assert response.status_code == 422


def test_list_stocks_rejects_limit_over_max(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks", params={"limit": 500})

    assert response.status_code == 422


def test_list_stocks_rejects_negative_offset(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/stocks", params={"offset": -1})

    assert response.status_code == 422
