"""UniverseMembershipEvent ORM model.

Logs every time a universe refresh adds or removes a symbol from the
active scan universe. `Stock.is_active` always reflects the *current*
membership (reused as-is, not duplicated); this table is the append-only
history behind it, so a future backtest can at least see when a symbol
entered/left the tracked universe - a partial mitigation of survivorship
bias, not a full point-in-time constituent dataset (NSE does not publish
historical NIFTY 500 membership as of this writing - see
`app/data/ingestion/nse_stock_list.py` and the README for this
limitation).
"""

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.stock import Stock

MEMBERSHIP_ACTIONS = ("added", "removed")


class UniverseMembershipEvent(Base):
    __tablename__ = "universe_membership_events"
    __table_args__ = (
        Index("ix_universe_membership_stock_universe", "stock_id", "universe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    universe: Mapped[str] = mapped_column(String(32), nullable=False, default="NIFTY500")
    action: Mapped[str] = mapped_column(String(8), nullable=False)
    effective_date: Mapped[date_type] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock: Mapped["Stock"] = relationship()
