"""Stock master (universe) service.

Manages the `Stock` table as a reference list of tradable symbols —
separate from `MarketDataService`, which handles price-history fetch and
persistence. Importing the stock universe never touches `PriceHistory` or
Yahoo Finance.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.stock import Stock


@dataclass
class ImportResult:
    records_seen: int
    created: int
    updated: int
    unchanged: int


def import_stocks(db: Session, records: list[dict[str, Any]]) -> ImportResult:
    """Idempotently upsert stock master records, keyed on `symbol`.

    A record for a symbol not yet in the table creates a new (active)
    `Stock` row. A record for an existing symbol updates `name`/`exchange`/
    `sector` only if they actually changed. Never produces duplicate
    `symbol` rows — `symbol` is already unique in the schema.
    """
    created = 0
    updated = 0
    unchanged = 0

    for record in records:
        symbol = record["symbol"].strip().upper()
        stock = db.scalar(select(Stock).where(Stock.symbol == symbol))

        if stock is None:
            db.add(
                Stock(
                    symbol=symbol,
                    name=record["name"],
                    exchange=record.get("exchange", "NSE"),
                    sector=record.get("sector"),
                    is_active=True,
                )
            )
            created += 1
            continue

        changed = False
        for field in ("name", "exchange", "sector"):
            value = record.get(field)
            if value is not None and getattr(stock, field) != value:
                setattr(stock, field, value)
                changed = True

        if changed:
            updated += 1
        else:
            unchanged += 1

    db.commit()

    return ImportResult(
        records_seen=len(records), created=created, updated=updated, unchanged=unchanged
    )


def list_stocks(
    db: Session,
    q: str | None = None,
    is_active: bool | None = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Stock], int]:
    """Search/filter/paginate the stock master, sorted stably by symbol."""
    filters = []
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Stock.symbol.ilike(pattern), Stock.name.ilike(pattern)))
    if is_active is not None:
        filters.append(Stock.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(Stock).where(*filters)) or 0

    rows = db.scalars(
        select(Stock).where(*filters).order_by(Stock.symbol).limit(limit).offset(offset)
    ).all()

    return list(rows), total
