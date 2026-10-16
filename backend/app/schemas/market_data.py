"""Pydantic schemas for market data API responses."""

from datetime import date

from pydantic import BaseModel

from app.schemas.price_history import PriceHistoryRead


class HistoricalPriceResponse(BaseModel):
    symbol: str
    exchange: str
    interval: str
    start_date: date
    end_date: date
    count: int
    prices: list[PriceHistoryRead]


class MarketDataSyncResponse(BaseModel):
    symbol: str
    interval: str
    start_date: date
    end_date: date
    records_fetched: int
    records_created: int
    records_skipped: int
