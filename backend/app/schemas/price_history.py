"""Pydantic schemas for the PriceHistory resource."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class PriceHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    interval: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int
