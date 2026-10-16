"""Market data provider abstraction.

Defines the interface that any market-data source must implement, so the
rest of the application (ingestion, processing, momentum engine) never
depends on a specific vendor. A concrete implementation such as
YahooFinanceProvider can be swapped for another provider later without
changing any calling code.

No network calls or data downloads happen here yet — this is intentionally
a skeleton to be implemented in a later step.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

VALID_INTERVALS: frozenset[str] = frozenset({"1d", "1wk", "1mo"})


class MarketDataProviderError(Exception):
    """Base exception for market data provider failures.

    Callers (services, routes) should depend on these exceptions rather
    than on any provider-specific exception type, so providers stay
    swappable.
    """


class SymbolNotFoundError(MarketDataProviderError):
    """Raised when the requested symbol does not exist with the provider."""


class NoDataFoundError(MarketDataProviderError):
    """Raised when the symbol is valid but has no data for the requested range."""


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_price_history(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> list[dict[str, Any]]:
        """Return OHLCV price records for a symbol between two dates.

        `interval` is one of VALID_INTERVALS ("1d", "1wk", "1mo").
        To be implemented by concrete providers.
        """
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        """Return the latest available price snapshot for a symbol.

        To be implemented by concrete providers.
        """
        raise NotImplementedError
