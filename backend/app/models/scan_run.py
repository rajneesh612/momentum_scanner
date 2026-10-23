"""ScanRun ORM model.

One row per attempted daily-scan execution (scheduled or manual) - the
audit trail for "did a scan happen, and what did it find". Folds in the
"optional daily scan summary" from the spec (symbol counts, signal
counts) rather than a separate summary table, since a 1:1 summary with no
independent lifecycle doesn't earn its own table.
"""

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.signal_event import SignalEvent

SCAN_RUN_STATUSES = ("running", "success", "partial_failure", "failed")
SCAN_RUN_TRIGGERS = ("scheduled", "manual")


class ScanRun(Base):
    """One execution of the daily hybrid-signal scan across the universe."""

    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    session_date: Mapped[date_type] = mapped_column(nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    universe_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_stale: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbols_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    buy_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sell_signals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Human-readable failure reason when status != "success" - never a
    # stack trace (no secrets, bounded length for API responses).
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    signal_events: Mapped[list["SignalEvent"]] = relationship(back_populates="scan_run")
