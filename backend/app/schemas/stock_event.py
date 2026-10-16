"""Pydantic schemas for the news/corporate-events API."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class StockEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stock_id: int
    title: str
    category: str
    summary: str | None
    published_at: datetime
    source_name: str
    source_url: str
    provider: str
    verification_status: str
    ingested_at: datetime


class StockEventListResponse(BaseModel):
    symbol: str
    category: str | None
    count: int
    events: list[StockEventRead]
    # True only when we have zero previously-ingested events AND the
    # live top-up attempt also failed/returned nothing — i.e. genuinely
    # no coverage right now, distinct from "no events match your filter".
    news_unavailable: bool


class EventImpactWindow(BaseModel):
    trading_days: int
    status: str  # "ok" | "pending" | "unavailable"
    stock_return_pct: float | None
    benchmark_return_pct: float | None
    relative_return_pct: float | None
    max_rise_pct: float | None
    max_drawdown_pct: float | None


class EventImpactResponse(BaseModel):
    event_id: int
    symbol: str
    event_date: date
    anchor_date: date | None
    benchmark_symbol: str
    benchmark_available: bool
    windows: list[EventImpactWindow]
    interpretation: list[str]
