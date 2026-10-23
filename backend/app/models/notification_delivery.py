"""NotificationDelivery ORM model.

One row per *attempt* to deliver a notification for a SignalEvent - never
per SignalEvent. A failed Telegram send is retried by inserting another
attempt row, not by mutating the SignalEvent, so retries can never
duplicate the underlying signal - only the delivery history grows.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.signal_event import SignalEvent

DELIVERY_STATUSES = ("pending", "sent", "failed")
DELIVERY_CHANNELS = ("telegram",)


class NotificationDelivery(Base):
    """One delivery attempt for one SignalEvent over one channel."""

    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_event_id: Mapped[int] = mapped_column(
        ForeignKey("signal_events.id", ondelete="CASCADE"), index=True, nullable=False
    )

    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="telegram")
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")

    # Never a secret (token/chat id) - just the HTTP status or a short,
    # human-readable transient-error description.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    signal_event: Mapped["SignalEvent"] = relationship()
