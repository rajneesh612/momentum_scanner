"""Telegram Bot API delivery, with bounded retries and backoff.

This project treats Telegram the way it treats every other external
dependency: through a small, swappable function, never scattered httpx
calls. `app/services/notification_service.py` is the only caller.

Delivery-reliability caveat (disclosed, not hidden): if a request times
out *after* Telegram has already accepted and queued the message, the
client has no way to know that happened, and a retry can then produce a
second, genuinely duplicate Telegram message. This module cannot, and
does not claim to, guarantee exactly-once delivery - only that a message
is never marked `sent` in the database unless Telegram's own response
confirmed `ok: true`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings

TELEGRAM_API_BASE = "https://api.telegram.org"


@dataclass
class TelegramSendResult:
    success: bool
    status_code: int | None
    error: str | None


def send_message(
    text: str,
    settings: Settings | None = None,
    timeout: float = 10.0,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
) -> TelegramSendResult:
    """Send one message, retrying transient failures (timeouts, 429, 5xx)
    with exponential backoff. Never retries a non-retryable 4xx (e.g. a
    bad token/chat id) - retrying that would just waste the whole budget
    on a request that can never succeed.
    """
    settings = settings or get_settings()

    if not settings.telegram_alerts_enabled:
        return TelegramSendResult(
            success=False, status_code=None, error="Telegram alerts are disabled."
        )
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return TelegramSendResult(
            success=False, status_code=None, error="Telegram bot token/chat id not configured."
        )

    url = f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": settings.telegram_chat_id, "text": text}

    last_error: str | None = None
    attempt = 0
    while attempt < max_retries:
        try:
            response = httpx.post(url, json=payload, timeout=timeout)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            last_error = f"Request error: {exc}"
            attempt += 1
            if attempt < max_retries:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
            continue

        if response.status_code == 200:
            body = response.json()
            if body.get("ok"):
                return TelegramSendResult(success=True, status_code=200, error=None)
            return TelegramSendResult(
                success=False,
                status_code=200,
                error=f"Telegram API error: {body.get('description', 'unknown')}",
            )

        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            attempt += 1
            if attempt < max_retries:
                time.sleep(backoff_seconds * (2 ** (attempt - 1)))
            continue

        # Non-retryable 4xx.
        return TelegramSendResult(
            success=False,
            status_code=response.status_code,
            error=f"HTTP {response.status_code}: {response.text[:200]}",
        )

    return TelegramSendResult(
        success=False, status_code=None, error=last_error or "Max retries exceeded."
    )
