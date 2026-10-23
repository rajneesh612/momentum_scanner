"""Tests for the Telegram delivery function - never makes a real HTTP call."""

from unittest.mock import MagicMock, patch

import httpx

from app.core.config import Settings
from app.services import telegram_service


def _settings(**overrides) -> Settings:
    base = {
        "telegram_alerts_enabled": True,
        "telegram_bot_token": "test-token",
        "telegram_chat_id": "12345",
    }
    base.update(overrides)
    return Settings(**base)


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"ok": True}
    return response


def test_disabled_never_calls_the_api() -> None:
    disabled_settings = _settings(telegram_alerts_enabled=False)
    with patch("app.services.telegram_service.httpx.post") as mock_post:
        result = telegram_service.send_message("hi", settings=disabled_settings)
    assert result.success is False
    assert "disabled" in result.error
    mock_post.assert_not_called()


def test_missing_credentials_never_calls_the_api() -> None:
    with patch("app.services.telegram_service.httpx.post") as mock_post:
        result = telegram_service.send_message(
            "hi", settings=_settings(telegram_bot_token="", telegram_chat_id="")
        )
    assert result.success is False
    mock_post.assert_not_called()


def test_success_marks_sent_only_after_ok_true() -> None:
    with patch(
        "app.services.telegram_service.httpx.post", return_value=_ok_response()
    ) as mock_post:
        result = telegram_service.send_message("hi", settings=_settings())
    assert result.success is True
    assert mock_post.call_count == 1


def test_telegram_level_failure_is_not_marked_sent() -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"ok": False, "description": "chat not found"}
    with patch("app.services.telegram_service.httpx.post", return_value=response):
        result = telegram_service.send_message("hi", settings=_settings())
    assert result.success is False
    assert "chat not found" in result.error


def test_timeout_then_success_retries_with_backoff() -> None:
    with (
        patch(
            "app.services.telegram_service.httpx.post",
            side_effect=[httpx.TimeoutException("timed out"), _ok_response()],
        ) as mock_post,
        patch("app.services.telegram_service.time.sleep") as mock_sleep,
    ):
        result = telegram_service.send_message(
            "hi", settings=_settings(), max_retries=3, backoff_seconds=1.0
        )
    assert result.success is True
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once()


def test_rate_limit_exhausts_retries_and_fails() -> None:
    response = MagicMock()
    response.status_code = 429
    response.text = "Too Many Requests"
    with (
        patch("app.services.telegram_service.httpx.post", return_value=response) as mock_post,
        patch("app.services.telegram_service.time.sleep"),
    ):
        result = telegram_service.send_message(
            "hi", settings=_settings(), max_retries=3, backoff_seconds=0.01
        )
    assert result.success is False
    assert mock_post.call_count == 3


def test_non_retryable_4xx_does_not_retry() -> None:
    response = MagicMock()
    response.status_code = 400
    response.text = "Bad Request"
    with patch("app.services.telegram_service.httpx.post", return_value=response) as mock_post:
        result = telegram_service.send_message("hi", settings=_settings(), max_retries=3)
    assert result.success is False
    assert mock_post.call_count == 1
