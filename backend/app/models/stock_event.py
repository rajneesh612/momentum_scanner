"""StockEvent ORM model.

A company news/corporate-event item (earnings, buyback, dividend, M&A,
order win, regulatory action, fundraising, or other material news)
associated with a Stock. Separate from PriceHistory — ingestion of events
and ingestion of OHLCV data are independent pipelines.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.stock import Stock

# Best-effort category classification — not authoritative structured data
# from any source, just a local heuristic over headline text. "other" is
# the honest default when nothing matches.
EVENT_CATEGORIES = (
    "earnings",
    "dividend",
    "buyback",
    "ma",
    "order_win",
    "regulatory",
    "fundraising",
    "other",
)


class StockEvent(Base):
    """A single news/corporate-event item for a stock.

    Deduplicated on (provider, provider_event_id) — re-ingesting the same
    article from the same provider never creates a duplicate row.
    """

    __tablename__ = "stock_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_event_id", name="uq_stock_events_provider_event_id"
        ),
        Index("ix_stock_events_stock_id_published_at", "stock_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # When the event was actually announced/published, per the source —
    # distinct from `ingested_at` (when our system first saw it). Always
    # stored timezone-aware in UTC.
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source_name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Which provider supplied this item, and that provider's own id for
    # the article — together the dedup key.
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # Honest provenance: single-source, nothing cross-checked against it.
    # "unverified" is the only value produced today; the column exists so
    # a future cross-source verification step has somewhere to write to
    # without a schema change.
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="unverified", server_default="unverified"
    )

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock: Mapped["Stock"] = relationship()
