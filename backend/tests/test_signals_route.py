"""Tests for the daily-scanner API routes: signals, scans, manual
trigger auth, Telegram test, strategy config, universe refresh, and the
hybrid backtester."""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_market_data_provider, get_market_data_service
from app.core.config import Settings, get_settings
from app.main import app
from app.models.price_history import PriceHistory
from app.models.stock import Stock
from app.services import scan_service
from app.services.market_data_service import MarketDataService
from app.services.telegram_service import TelegramSendResult
from tests.fakes import FakeMarketDataProvider


@pytest.fixture(autouse=True)
def _stub_market_data_provider():
    app.dependency_overrides[get_market_data_provider] = lambda: FakeMarketDataProvider(
        daily_prices=[]
    )
    app.dependency_overrides[get_market_data_service] = lambda: MarketDataService(
        FakeMarketDataProvider(daily_prices=[])
    )
    yield


@pytest.fixture
def api_key_settings(monkeypatch: pytest.MonkeyPatch):
    settings = Settings(scan_api_key="test-key")
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings


@pytest.fixture
def no_api_key_settings(monkeypatch: pytest.MonkeyPatch):
    # Explicit, not "whatever happens to be in backend/.env on this
    # machine" - these tests assert the *unconfigured* 503 path, which
    # must hold regardless of a developer's local .env contents.
    settings = Settings(scan_api_key="", _env_file=None)
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings


@pytest.fixture
def patched_session_local(db_session: Session, monkeypatch: pytest.MonkeyPatch):
    test_sessionmaker = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    monkeypatch.setattr(scan_service, "SessionLocal", test_sessionmaker)
    return test_sessionmaker


def test_latest_signals_empty(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/signals/latest")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_latest_scan_404_before_any_run(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/scans/latest")
    assert response.status_code == 404


def test_strategy_config_returns_defaults(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/strategy-config")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "hybrid_daily"
    assert body["sma_mid"] == 50
    assert body["sma_long"] == 200


def test_manual_scan_disabled_without_api_key_configured(
    db_client: TestClient, no_api_key_settings
) -> None:
    response = db_client.post("/api/v1/scans/run")
    assert response.status_code == 503


def test_manual_scan_rejects_wrong_api_key(db_client: TestClient, api_key_settings) -> None:
    response = db_client.post("/api/v1/scans/run", headers={"X-Scan-Api-Key": "wrong"})
    assert response.status_code == 401


def test_scan_api_key_loads_from_an_env_file_through_the_live_request_path(
    db_client: TestClient, tmp_path
) -> None:
    """Regression test for a real incident: SCAN_API_KEY was visibly set
    in backend/.env, but requests to /scans/run kept reporting it as
    unconfigured (503). Root cause was `env_file=".env"` being resolved
    relative to the process's cwd rather than config.py's own location.

    This exercises the fix through the *actual* FastAPI dependency chain
    requests use (deps.require_scan_api_key -> Depends(get_settings) ->
    Settings.scan_api_key) - not just a standalone `Settings()` call -
    using a temp .env file at an explicit absolute path so it's portable
    and doesn't depend on any developer's real backend/.env contents.
    """
    env_path = tmp_path / "regression.env"
    env_path.write_text("SCAN_API_KEY=regression-key\n", encoding="utf-8")

    settings = Settings(_env_file=env_path)
    app.dependency_overrides[get_settings] = lambda: settings

    # Wrong key: 401, not 503 - proves the key loaded from the file (a
    # key that was never configured always returns 503, regardless of
    # what header is sent - see test_manual_scan_disabled_without_api_key_configured).
    wrong = db_client.post("/api/v1/scans/run", headers={"X-Scan-Api-Key": "not-it"})
    assert wrong.status_code == 401

    # Correct key: passes auth and reaches the handler (the subsequent
    # 200/4xx/5xx then depends on universe/DB state, which this test
    # doesn't care about - only that auth itself succeeded).
    correct = db_client.post("/api/v1/scans/run", headers={"X-Scan-Api-Key": "regression-key"})
    assert correct.status_code != 401
    assert correct.status_code != 503


def test_manual_scan_runs_with_correct_api_key(
    db_client: TestClient, api_key_settings, patched_session_local, db_session: Session
) -> None:
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE", is_active=True)
    db_session.add(stock)
    db_session.commit()

    response = db_client.post(
        "/api/v1/scans/run",
        headers={"X-Scan-Api-Key": "test-key"},
        params={"session_date": "2024-06-01"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["universe_size"] == 1
    assert "data_quality_report" in body


def test_telegram_test_requires_api_key(db_client: TestClient, no_api_key_settings) -> None:
    response = db_client.post("/api/v1/telegram/test")
    assert response.status_code == 503


def test_telegram_test_with_api_key_calls_telegram_service(
    db_client: TestClient, api_key_settings
) -> None:
    with patch(
        "app.services.telegram_service.send_message",
        return_value=TelegramSendResult(success=True, status_code=200, error=None),
    ):
        response = db_client.post("/api/v1/telegram/test", headers={"X-Scan-Api-Key": "test-key"})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_universe_refresh_requires_api_key(db_client: TestClient, no_api_key_settings) -> None:
    response = db_client.post("/api/v1/universe/refresh")
    assert response.status_code == 503


def test_hybrid_backtest_route(db_client: TestClient, db_session: Session) -> None:
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE")
    db_session.add(stock)
    db_session.flush()

    start = date(2023, 1, 1)
    for i in range(260):
        close = 100 + (i % 50) * 0.5
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

    response = db_client.post(
        "/api/v1/backtest/hybrid/AAA.NS",
        params={
            "start_date": (start + timedelta(days=250)).isoformat(),
            "end_date": (start + timedelta(days=259)).isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AAA.NS"
    assert body["strategy"] == "hybrid_daily"
    assert "sharpe_ratio" in body["summary"]
