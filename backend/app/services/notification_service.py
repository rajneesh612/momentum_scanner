"""Formats and delivers a SignalEvent's Telegram notification.

Idempotent by construction: before sending, this checks whether the
SignalEvent already has a `sent` NotificationDelivery and, if so, does
nothing (safe to call this twice for the same event). A failed attempt
inserts a new `NotificationDelivery` row and leaves the SignalEvent
itself untouched, so retrying can never create a duplicate signal - only
another attempt row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification_delivery import NotificationDelivery
from app.models.signal_event import SignalEvent
from app.momentum.hybrid_signal import BUY, HybridStrategyConfig
from app.services import telegram_service

_currency = "₹"  # Rupee sign - avoids a literal non-ASCII char in source.


@dataclass
class NotificationOutcome:
    attempted: bool
    success: bool
    reason: str | None = None


def format_message(event: SignalEvent, symbol: str, config: HybridStrategyConfig) -> str:
    indicators: dict = json.loads(event.indicators_json)
    session = event.session_date.isoformat()
    price = f"{_currency}{event.price:,.2f}"

    if event.signal_type == BUY:
        mom_short = indicators.get("momentum_short_pct")
        mom_long = indicators.get("momentum_long_pct")
        volume_avg = indicators.get("volume_avg")
        volume = indicators.get("volume")
        volume_ratio = volume / volume_avg if volume is not None and volume_avg else None
        exit_line = f"Trend: Close > SMA{config.sma_mid} > SMA{config.sma_long}"
        volume_line = f"Volume vs {config.volume_lookback}-day average: {_ratio(volume_ratio)}"
        return (
            f"\U0001f4c8 BUY SIGNAL — {symbol}\n\n"
            f"Session: {session}\n"
            f"Close: {price}\n"
            f"{exit_line}\n"
            f"{config.momentum_short_days}-session momentum: {_pct(mom_short)}\n"
            f"~12-month momentum: {_pct(mom_long)}\n"
            f"{volume_line}\n"
            f"Strategy: {config.name} {config.version}\n\n"
            "This is a strategy-generated signal, not a guaranteed trading recommendation."
        )

    exit_reason = (
        f"Close below SMA{config.sma_mid}, or SMA{config.sma_mid} below SMA{config.sma_long}"
    )
    return (
        f"\U0001f4c9 SELL SIGNAL — {symbol}\n\n"
        f"Session: {session}\n"
        f"Close: {price}\n"
        f"Exit reason: {exit_reason}\n"
        f"Strategy: {config.name} {config.version}\n\n"
        "This is a strategy-generated exit signal, not a prediction of future price."
    )


def _pct(value: float | None) -> str:
    return f"{value:+.2f}%" if value is not None else "n/a"


def _ratio(value: float | None) -> str:
    return f"{value:.2f}x" if value is not None else "n/a"


def has_been_sent(db: Session, signal_event_id: int) -> bool:
    return (
        db.scalar(
            select(NotificationDelivery.id).where(
                NotificationDelivery.signal_event_id == signal_event_id,
                NotificationDelivery.status == "sent",
            )
        )
        is not None
    )


def deliver(
    db: Session,
    event: SignalEvent,
    symbol: str,
    config: HybridStrategyConfig,
    max_retries: int = 3,
    backoff_seconds: float = 2.0,
) -> NotificationOutcome:
    """Send (or retry) the Telegram notification for one SignalEvent."""
    if has_been_sent(db, event.id):
        return NotificationOutcome(attempted=False, success=True, reason="already sent")

    prior_attempts = db.scalar(
        select(NotificationDelivery.attempt_number)
        .where(NotificationDelivery.signal_event_id == event.id)
        .order_by(NotificationDelivery.attempt_number.desc())
        .limit(1)
    )
    attempt_number = (prior_attempts or 0) + 1

    delivery = NotificationDelivery(
        signal_event_id=event.id,
        channel="telegram",
        attempt_number=attempt_number,
        status="pending",
    )
    db.add(delivery)
    db.flush()

    text = format_message(event, symbol, config)
    result = telegram_service.send_message(
        text, max_retries=max_retries, backoff_seconds=backoff_seconds
    )

    if result.success:
        delivery.status = "sent"
        from datetime import datetime

        delivery.delivered_at = datetime.now(UTC)
        event.notification_status = "sent"
    else:
        delivery.status = "failed"
        delivery.last_error = result.error
        event.notification_status = "failed"

    db.commit()
    return NotificationOutcome(attempted=True, success=result.success, reason=result.error)
