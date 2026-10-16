"""Test doubles for market data provider tests.

Used so unit/integration tests never make real Yahoo Finance network calls.
"""

from datetime import date
from typing import Any

from app.data.ingestion.news_provider import NewsProvider, RawEvent
from app.data.ingestion.provider import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    """A MarketDataProvider stub whose behavior is fixed at construction time."""

    def __init__(
        self,
        daily_prices: list[dict[str, Any]] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._daily_prices = daily_prices or []
        self._raise_error = raise_error

    def get_price_history(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> list[dict[str, Any]]:
        if self._raise_error is not None:
            raise self._raise_error
        return self._daily_prices

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError


class FakeNewsProvider(NewsProvider):
    """A NewsProvider stub whose behavior is fixed at construction time."""

    def __init__(
        self,
        events: list[RawEvent] | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self._events = events or []
        self._raise_error = raise_error

    def get_events(self, symbol: str, count: int = 20) -> list[RawEvent]:
        if self._raise_error is not None:
            raise self._raise_error
        return self._events
