"""NIFTY 500 scan-universe management.

Builds on `app/services/stock_service.py` (the generic Stock-table
upsert) rather than duplicating it, and adds the scanner-specific pieces
that module intentionally doesn't do: deactivating symbols that dropped
out of the published list (never deleting them - history must survive),
logging every add/remove as a `UniverseMembershipEvent`, and reporting
per-record validation problems instead of silently dropping rows.

Universe refresh is a deliberately separate operation from the daily
scan (see `app/services/scan_service.py`) - refreshing can be slow/flaky
(network call to NSE) and scanning must be able to run against whatever
universe was last successfully imported even if today's refresh failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.ingestion.nse_stock_list import StockListFetchError, fetch_nifty500
from app.models.stock import Stock
from app.models.universe_membership import UniverseMembershipEvent

DEFAULT_UNIVERSE = "NIFTY500"


@dataclass
class UniverseRefreshResult:
    universe: str
    source_fetch_succeeded: bool
    records_seen: int
    created: int
    updated: int
    unchanged: int
    deactivated: int
    invalid_records: list[str] = field(default_factory=list)
    duplicate_symbols: list[str] = field(default_factory=list)
    error: str | None = None


def _validate_records(records: list[dict]) -> tuple[list[dict], list[str], list[str]]:
    """Separate out invalid/duplicate rows instead of silently dropping them."""
    valid: list[dict] = []
    invalid: list[str] = []
    seen: set[str] = set()
    duplicates: list[str] = []

    for record in records:
        symbol = (record.get("symbol") or "").strip().upper()
        name = (record.get("name") or "").strip()
        if not symbol or not name:
            invalid.append(f"{record!r} - missing symbol or name")
            continue
        if symbol in seen:
            duplicates.append(symbol)
            continue
        seen.add(symbol)
        valid.append({**record, "symbol": symbol})

    return valid, invalid, duplicates


def refresh_universe(
    db: Session,
    source: str | None = None,
    universe: str = DEFAULT_UNIVERSE,
    effective_date: date | None = None,
) -> UniverseRefreshResult:
    """Fetch the current constituent list and reconcile it against `Stock`.

    If the fetch itself fails (NSE unreachable, malformed CSV), the
    existing universe is left completely untouched - this returns a
    result with `source_fetch_succeeded=False` and an `error`, never an
    empty/partial universe. Callers should report the age of the last
    successful refresh (derivable from the latest `UniverseMembershipEvent`
    or `Stock.updated_at`) alongside this.
    """
    effective_date = effective_date or date.today()

    try:
        records = fetch_nifty500(source=source)
    except StockListFetchError as exc:
        return UniverseRefreshResult(
            universe=universe,
            source_fetch_succeeded=False,
            records_seen=0,
            created=0,
            updated=0,
            unchanged=0,
            deactivated=0,
            error=str(exc),
        )

    valid_records, invalid, duplicates = _validate_records(records)
    fetched_symbols = {r["symbol"] for r in valid_records}

    created = 0
    updated = 0
    unchanged = 0

    for record in valid_records:
        stock = db.scalar(select(Stock).where(Stock.symbol == record["symbol"]))
        if stock is None:
            stock = Stock(
                symbol=record["symbol"],
                name=record["name"],
                exchange=record.get("exchange", "NSE"),
                sector=record.get("sector"),
                is_active=True,
            )
            db.add(stock)
            db.flush()
            created += 1
            db.add(
                UniverseMembershipEvent(
                    stock_id=stock.id,
                    universe=universe,
                    action="added",
                    effective_date=effective_date,
                    source="nse_nifty500_csv",
                )
            )
            continue

        changed = False
        for field_name in ("name", "exchange", "sector"):
            value = record.get(field_name)
            if value is not None and getattr(stock, field_name) != value:
                setattr(stock, field_name, value)
                changed = True
        if not stock.is_active:
            stock.is_active = True
            changed = True
            db.add(
                UniverseMembershipEvent(
                    stock_id=stock.id,
                    universe=universe,
                    action="added",
                    effective_date=effective_date,
                    source="nse_nifty500_csv",
                )
            )

        if changed:
            updated += 1
        else:
            unchanged += 1

    # Deactivate (never delete) any currently-active stock in this
    # universe that the fresh list no longer contains.
    currently_active = db.scalars(
        select(Stock).where(Stock.is_active == True, Stock.exchange == "NSE")  # noqa: E712
    ).all()
    deactivated = 0
    for stock in currently_active:
        if stock.symbol not in fetched_symbols:
            stock.is_active = False
            deactivated += 1
            db.add(
                UniverseMembershipEvent(
                    stock_id=stock.id,
                    universe=universe,
                    action="removed",
                    effective_date=effective_date,
                    source="nse_nifty500_csv",
                )
            )

    db.commit()

    return UniverseRefreshResult(
        universe=universe,
        source_fetch_succeeded=True,
        records_seen=len(records),
        created=created,
        updated=updated,
        unchanged=unchanged,
        deactivated=deactivated,
        invalid_records=invalid,
        duplicate_symbols=duplicates,
    )


def active_universe(db: Session, exchange: str = "NSE") -> list[Stock]:
    """The current scan universe - every active Stock on the given exchange."""
    return list(
        db.scalars(
            select(Stock)
            .where(Stock.is_active == True, Stock.exchange == exchange)  # noqa: E712
            .order_by(Stock.symbol)
        ).all()
    )


def last_refresh_at(db: Session, universe: str = DEFAULT_UNIVERSE) -> date | None:
    """The most recent membership-event date, as a proxy for "how old is
    the current universe". None if a refresh has never run."""
    latest = db.scalar(
        select(UniverseMembershipEvent.effective_date)
        .where(UniverseMembershipEvent.universe == universe)
        .order_by(UniverseMembershipEvent.effective_date.desc())
        .limit(1)
    )
    return latest
