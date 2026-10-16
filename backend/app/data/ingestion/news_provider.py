"""News/corporate-event provider abstraction.

Defines the interface any news source must implement, mirroring
`app/data/ingestion/provider.py`'s MarketDataProvider pattern, so the rest
of the app never depends on a specific vendor and a concrete provider can
be swapped without changing calling code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class NewsProviderError(Exception):
    """Base exception for news provider failures.

    Callers should depend on this (and its subclasses) rather than any
    provider-specific exception type, so providers stay swappable.
    """


class NewsRateLimitError(NewsProviderError):
    """Raised when the provider's rate limit is hit."""


@dataclass
class RawEvent:
    """A single news/event item exactly as parsed from a provider.

    Every field here must come from the provider's own data — nothing is
    inferred or invented. `category` is the one exception: it's a local
    best-effort classification over `title`, not data the provider itself
    supplies structured.
    """

    provider: str
    provider_event_id: str
    title: str
    category: str
    summary: str | None
    published_at: datetime  # timezone-aware, UTC
    source_name: str
    source_url: str


class NewsProvider(ABC):
    """Abstract base class for news/corporate-event providers."""

    @abstractmethod
    def get_events(self, symbol: str, count: int = 20) -> list[RawEvent]:
        """Return recent news/event items for a symbol.

        Providers are not guaranteed to support arbitrary historical date
        ranges — most free/unofficial news endpoints only expose recent
        items. Callers must not assume exhaustive historical coverage;
        `count` is a best-effort cap on how many recent items to fetch.
        """
        raise NotImplementedError
