"""Pydantic schemas for the Stock resource."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    exchange: str
    sector: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StockListResponse(BaseModel):
    items: list[StockRead]
    total: int
    limit: int
    offset: int
