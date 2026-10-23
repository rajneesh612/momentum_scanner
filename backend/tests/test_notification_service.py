"""Tests for notification formatting and idempotent delivery."""

import json
from datetime import date
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification_delivery import NotificationDelivery
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.momentum.hybrid_signal import HybridStrategyConfig
from app.services import notification_service
from app.services.telegram_service import TelegramSendResult

_CONFIG = HybridStrategyConfig()


def _make_event(db: Session, signal_type: str = "BUY") -> SignalEvent:
    stock = Stock(symbol="AAA.NS", name="AAA Ltd", exchange="NSE")
    db.add(stock)
    db.flush()
    event = SignalEvent(
        stock_id=stock.id,
        strategy_name=_CONFIG.name,
        strategy_version=_CONFIG.version,
        session_date=date(2024, 1, 10),
        signal_type=signal_type,
        price=123.45,
        indicators_json=json.dumps(
            {
                "momentum_short_pct": 5.0,
                "momentum_long_pct": 20.0,
                "volume_avg": 1000.0,
                "volume": 1500.0,
            }
        ),
        data_quality_status="ok",
        notification_status="pending",
    )
    db.add(event)
    db.commit()
    return event


def test_buy_message_includes_symbol_price_and_disclaimer() -> None:
    event = SignalEvent(
        session_date=date(2024, 1, 10),
        signal_type="BUY",
        price=123.45,
        indicators_json=json.dumps(
            {
                "momentum_short_pct": 5.0,
                "momentum_long_pct": 20.0,
                "volume_avg": 100.0,
                "volume": 150.0,
            }
        ),
    )
    text = notification_service.format_message(event, "AAA.NS", _CONFIG)
    assert "BUY SIGNAL" in text
    assert "AAA.NS" in text
    assert "123.45" in text
    assert "1.50x" in text  # volume / volume_avg
    assert "not a guaranteed trading recommendation" in text


def test_sell_message_states_exit_reason() -> None:
    event = SignalEvent(
        session_date=date(2024, 1, 10), signal_type="SELL", price=99.0, indicators_json="{}"
    )
    text = notification_service.format_message(event, "AAA.NS", _CONFIG)
    assert "SELL SIGNAL" in text
    assert f"SMA{_CONFIG.sma_mid}" in text
    assert "not a prediction of future price" in text


def test_deliver_marks_sent_on_success(db_session: Session) -> None:
    event = _make_event(db_session)
    with patch(
        "app.services.telegram_service.send_message",
        return_value=TelegramSendResult(success=True, status_code=200, error=None),
    ):
        outcome = notification_service.deliver(db_session, event, "AAA.NS", _CONFIG)

    assert outcome.success is True
    db_session.refresh(event)
    assert event.notification_status == "sent"
    deliveries = db_session.scalars(select(NotificationDelivery)).all()
    assert len(deliveries) == 1
    assert deliveries[0].status == "sent"


def test_deliver_is_idempotent_once_sent(db_session: Session) -> None:
    event = _make_event(db_session)
    with patch(
        "app.services.telegram_service.send_message",
        return_value=TelegramSendResult(success=True, status_code=200, error=None),
    ) as mock_send:
        notification_service.deliver(db_session, event, "AAA.NS", _CONFIG)
        outcome = notification_service.deliver(db_session, event, "AAA.NS", _CONFIG)

    assert outcome.attempted is False
    assert outcome.success is True
    mock_send.assert_called_once()  # second deliver() never hit Telegram again


def test_failed_delivery_is_retryable_without_duplicating_the_signal(db_session: Session) -> None:
    event = _make_event(db_session)
    event_id = event.id

    with patch(
        "app.services.telegram_service.send_message",
        return_value=TelegramSendResult(success=False, status_code=500, error="server error"),
    ):
        first = notification_service.deliver(db_session, event, "AAA.NS", _CONFIG)

    with patch(
        "app.services.telegram_service.send_message",
        return_value=TelegramSendResult(success=True, status_code=200, error=None),
    ):
        second = notification_service.deliver(db_session, event, "AAA.NS", _CONFIG)

    assert first.success is False
    assert second.success is True

    # Exactly one SignalEvent still exists - retries only ever add
    # NotificationDelivery rows.
    assert db_session.scalar(select(SignalEvent)).id == event_id
    deliveries = db_session.scalars(
        select(NotificationDelivery).where(NotificationDelivery.signal_event_id == event_id)
    ).all()
    assert len(deliveries) == 2
    assert [d.attempt_number for d in deliveries] == [1, 2]
    assert deliveries[0].status == "failed"
    assert deliveries[1].status == "sent"
