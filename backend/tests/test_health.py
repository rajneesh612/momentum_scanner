"""Tests for the health/status endpoints."""

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "app_name" in body


def test_root_endpoint_returns_api_info(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert "message" in body
    assert body["docs_url"] == "/docs"
