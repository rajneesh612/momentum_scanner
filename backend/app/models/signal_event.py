"""SignalEvent ORM model.

One row per *transition* the hybrid scanner detected for a stock (a fresh
BUY or a fresh SELL/exit) - never one row per day a condition merely
continues to hold. See `app/services/signal_service.py` for how the
previous state is derived (from the latest prior SignalEvent for the same
stock+strategy, read fresh from the DB every scan - never from in-memory
state, so this survives process restarts).
"""

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.scan_run import ScanRun
    from app.models.stock import Stock

SIGNAL_TYPES = ("BUY", "SELL")
DATA_QUALITY_STATUSES = ("ok", "insufficient", "stale", "missing")
NOTIFICATION_STATUSES = ("not_applicable", "pending", "sent", "failed")


class SignalEvent(Base):
    """A single BUY/SELL transition produced by one strategy version.

    Deduplicated on (stock_id, strategy_name, strategy_version,
    session_date, signal_type): this is a backstop against concurrent
    scans racing on the same session, not the primary dedup mechanism -
    the primary mechanism is that `signal_service` only ever calls
    `evaluate_latest` with the correct prior state, so it only *attempts*
    to insert a transition in the first place. If two scan workers
    somehow both attempt it for the same session, the loser's insert
    fails this constraint and is treated as "already recorded", not an
    error.
    """

    __tablename__ = "signal_events"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "strategy_name",
            "strategy_version",
            "session_date",
            "signal_type",
            name="uq_signal_events_identity",
        ),
        Index(
            "ix_signal_events_stock_strategy_session", "stock_id", "strategy_name", "session_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scan_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True
    )

    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)

    session_date: Mapped[date_type] = mapped_column(nullable=False)
    signal_type: Mapped[str] = mapped_column(String(8), nullable=False)

    price: Mapped[float] = mapped_column(Float, nullable=False)
    # Indicator snapshot at signal time (sma_short/mid/long, volume_avg,
    # momentum_short_pct, momentum_long_pct, volatility_pct) - stored as
    # plain JSON-able text so this stays readable without a JSON column
    # type difference between SQLite (tests) and Postgres (prod).
    indicators_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    data_quality_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ok", server_default="ok"
    )
    notification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="not_applicable", server_default="not_applicable"
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock: Mapped["Stock"] = relationship()
    scan_run: Mapped["ScanRun | None"] = relationship(back_populates="signal_events")
