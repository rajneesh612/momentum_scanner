"""PriceHistory ORM model."""

from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.stock import Stock


class PriceHistory(Base):
    """A single bar's OHLCV record for a stock, at a given interval.

    A (stock_id, date, interval) unique constraint prevents duplicate
    records for the same stock/bar — daily, weekly, and monthly bars for
    the same stock/date coexist as separate rows.
    """

    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "date", "interval", name="uq_price_history_stock_id_date_interval"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[date_type] = mapped_column(Date, index=True, nullable=False)
    interval: Mapped[str] = mapped_column(String(8), nullable=False, server_default="1d")
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock: Mapped["Stock"] = relationship(back_populates="price_history")
