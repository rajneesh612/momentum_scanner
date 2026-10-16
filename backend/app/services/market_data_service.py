"""Market data service.

Coordinates fetching data through a MarketDataProvider and persisting it
via SQLAlchemy models. Routes call this service; the service is the only
layer that knows about both the provider abstraction and the database
models. Provider-specific (e.g. yfinance) details never leak in here —
only the MarketDataProvider interface and its shared exceptions are used.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.data.ingestion.provider import MarketDataProvider
from app.models.price_history import PriceHistory
from app.models.stock import Stock


class StockNotFoundError(Exception):
    """Raised when a symbol has no Stock record in the database yet."""


class MarketDataPersistenceError(Exception):
    """Raised when saving fetched market data to the database fails."""


@dataclass
class SyncResult:
    symbol: str
    interval: str
    start_date: date
    end_date: date
    records_fetched: int
    records_created: int
    records_skipped: int


class MarketDataService:
    """Fetches and persists market data, keeping routes free of that logic."""

    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

    def sync_symbol_history(
        self, db: Session, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> SyncResult:
        """Fetch prices from the provider and persist new records."""
        symbol = symbol.strip().upper()
        records = self._provider.get_price_history(symbol, start, end, interval)

        stock = self._get_or_create_stock(db, symbol)
        existing_dates = self._existing_price_dates(db, stock.id, interval, start, end)

        created = 0
        for record in records:
            if record["date"] in existing_dates:
                continue

            db.add(
                PriceHistory(
                    stock_id=stock.id,
                    date=record["date"],
                    interval=interval,
                    open=record["open"],
                    high=record["high"],
                    low=record["low"],
                    close=record["close"],
                    adjusted_close=record["adjusted_close"],
                    volume=record["volume"],
                )
            )
            existing_dates.add(record["date"])
            created += 1

        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise MarketDataPersistenceError(
                f"Failed to save price history for '{symbol}'."
            ) from exc

        return SyncResult(
            symbol=symbol,
            interval=interval,
            start_date=start,
            end_date=end,
            records_fetched=len(records),
            records_created=created,
            records_skipped=len(records) - created,
        )

    def get_price_history(
        self, db: Session, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> tuple[Stock, list[PriceHistory]]:
        """Read previously-synced price history for a symbol from the database."""
        symbol = symbol.strip().upper()
        stock = db.scalar(select(Stock).where(Stock.symbol == symbol))
        if stock is None:
            raise StockNotFoundError(f"Stock '{symbol}' was not found.")

        rows = db.scalars(
            select(PriceHistory)
            .where(
                PriceHistory.stock_id == stock.id,
                PriceHistory.interval == interval,
                PriceHistory.date >= start,
                PriceHistory.date <= end,
            )
            .order_by(PriceHistory.date)
        ).all()

        return stock, list(rows)

    def _get_or_create_stock(self, db: Session, symbol: str) -> Stock:
        stock = db.scalar(select(Stock).where(Stock.symbol == symbol))
        if stock is not None:
            return stock

        stock = Stock(symbol=symbol, name=symbol, exchange=self._infer_exchange(symbol))
        db.add(stock)
        db.flush()
        return stock

    @staticmethod
    def _infer_exchange(symbol: str) -> str:
        if symbol.startswith("^"):
            return "INDEX"
        if symbol.endswith(".NS"):
            return "NSE"
        if symbol.endswith(".BO"):
            return "BSE"
        return "UNKNOWN"

    @staticmethod
    def _existing_price_dates(
        db: Session, stock_id: int, interval: str, start: date, end: date
    ) -> set[date]:
        rows = db.scalars(
            select(PriceHistory.date).where(
                PriceHistory.stock_id == stock_id,
                PriceHistory.interval == interval,
                PriceHistory.date >= start,
                PriceHistory.date <= end,
            )
        ).all()
        return set(rows)
