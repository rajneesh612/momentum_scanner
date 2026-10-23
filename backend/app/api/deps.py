"""Shared FastAPI dependency providers for API routes.

Routes depend on these functions (not on concrete provider/service
classes directly) so tests can override them via
`app.dependency_overrides` — e.g. swapping in a mock MarketDataProvider
without ever hitting the real Yahoo Finance API.
"""

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.data.ingestion.news_provider import NewsProvider
from app.data.ingestion.nse_announcements import NseAnnouncementsProvider
from app.data.ingestion.provider import MarketDataProvider
from app.data.ingestion.yahoo_finance import YahooFinanceProvider
from app.services.market_data_service import MarketDataService


def get_market_data_provider() -> MarketDataProvider:
    return YahooFinanceProvider()


def get_market_data_service(
    provider: MarketDataProvider = Depends(get_market_data_provider),
) -> MarketDataService:
    return MarketDataService(provider)


def get_news_provider() -> NewsProvider:
    # NSE's own corporate-announcements feed, verified live and reachable
    # with no API key — see nse_announcements.py's module docstring for
    # coverage/reliability caveats. YahooNewsProvider remains available
    # (app/data/ingestion/yahoo_news.py) as a swappable alternative; it
    # was not used here because live testing found it returns zero
    # results for every symbol in this environment.
    return NseAnnouncementsProvider()


def require_scan_api_key(
    x_scan_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Protects manual-scan-trigger and Telegram-test endpoints.

    Requires `SCAN_API_KEY` to be explicitly configured (a blank/unset
    key always rejects, rather than defaulting to "open") - see
    `.env.example`.
    """
    if not settings.scan_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SCAN_API_KEY is not configured - this endpoint is disabled.",
        )
    if x_scan_api_key != settings.scan_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Scan-Api-Key header.",
        )
