"""Company news/event service.

Ingests and serves StockEvent records — kept separate from
MarketDataService (which handles OHLCV price history); a different
pipeline, a different provider abstraction. Never creates a Stock row
itself — events only attach to stocks that already exist (via market-data
sync or the stock-master import), so a news item never invents a company
association.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.ingestion.news_provider import NewsProvider
from app.models.stock import Stock
from app.models.stock_event import StockEvent
from app.services.market_data_service import StockNotFoundError

__all__ = ["EventIngestResult", "StockNotFoundError", "ingest_events", "list_events"]


@dataclass
class EventIngestResult:
    symbol: str
    records_seen: int
    created: int
    skipped: int


def _get_stock(db: Session, symbol: str) -> Stock:
    symbol = symbol.strip().upper()
    stock = db.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        raise StockNotFoundError(f"Stock '{symbol}' was not found.")
    return stock


def ingest_events(
    db: Session, provider: NewsProvider, symbol: str, count: int = 20
) -> EventIngestResult:
    """Fetch recent news for `symbol` and persist new (deduplicated) events.

    Idempotent — re-running never creates duplicates, keyed on
    `(provider, provider_event_id)`. Raises StockNotFoundError if `symbol`
    hasn't been synced/imported yet — ingestion never creates the Stock
    row itself.
    """
    stock = _get_stock(db, symbol)
    raw_events = provider.get_events(symbol, count=count)

    existing_pairs = set(
        db.execute(select(StockEvent.provider, StockEvent.provider_event_id)).all()
    )

    created = 0
    for event in raw_events:
        key = (event.provider, event.provider_event_id)
        if key in existing_pairs:
            continue

        db.add(
            StockEvent(
                stock_id=stock.id,
                title=event.title,
                category=event.category,
                summary=event.summary,
                published_at=event.published_at,
                source_name=event.source_name,
                source_url=event.source_url,
                provider=event.provider,
                provider_event_id=event.provider_event_id,
            )
        )
        existing_pairs.add(key)
        created += 1

    db.commit()

    return EventIngestResult(
        symbol=stock.symbol,
        records_seen=len(raw_events),
        created=created,
        skipped=len(raw_events) - created,
    )


def list_events(
    db: Session,
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
) -> tuple[Stock, list[StockEvent]]:
    """Read previously-ingested events for a symbol.

    Filters on `published_at` (UTC) and `category`; sorted by
    `published_at` ascending (stable).
    """
    stock = _get_stock(db, symbol)

    filters = [StockEvent.stock_id == stock.id]
    if start_date is not None:
        filters.append(StockEvent.published_at >= datetime.combine(start_date, time.min, UTC))
    if end_date is not None:
        filters.append(StockEvent.published_at <= datetime.combine(end_date, time.max, UTC))
    if category is not None:
        filters.append(StockEvent.category == category)

    rows = db.scalars(
        select(StockEvent).where(*filters).order_by(StockEvent.published_at)
    ).all()

    return stock, list(rows)


def get_event(db: Session, event_id: int) -> StockEvent | None:
    return db.get(StockEvent, event_id)
