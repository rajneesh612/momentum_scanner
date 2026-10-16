"""News/corporate-event API routes."""

import contextlib
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_service, get_news_provider
from app.core.database import get_db
from app.data.ingestion.news_provider import NewsProvider, NewsProviderError
from app.models.stock_event import EVENT_CATEGORIES
from app.momentum.event_impact import build_interpretation
from app.schemas.stock_event import (
    EventImpactResponse,
    EventImpactWindow,
    StockEventListResponse,
    StockEventRead,
)
from app.services import event_service
from app.services.event_impact_service import DEFAULT_BENCHMARK_SYMBOL, compute_impact_for_event
from app.services.market_data_service import MarketDataService, StockNotFoundError

router = APIRouter(prefix="/stocks", tags=["events"])


@router.get("/{symbol}/events", response_model=StockEventListResponse)
def list_stock_events(
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    news_provider: NewsProvider = Depends(get_news_provider),
) -> StockEventListResponse:
    """List news/corporate events for a stock.

    Attempts a best-effort live top-up from the news provider first (never
    blocks the response if it fails — see `NewsProvider` implementations
    for current coverage limitations), then reads whatever is stored,
    filtered by date range (on `published_at`) and category.
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must not be after end_date.",
        )
    if category is not None and category not in EVENT_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"category must be one of {sorted(EVENT_CATEGORIES)}.",
        )

    # Best-effort: an unreachable/empty provider or an unknown symbol here
    # just means no top-up happened - handled honestly below, not a hard
    # failure of the whole request.
    with contextlib.suppress(NewsProviderError, StockNotFoundError):
        event_service.ingest_events(db, news_provider, symbol)

    try:
        stock, events = event_service.list_events(db, symbol, start_date, end_date, category)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    news_unavailable = False
    if not events:
        _, any_events = event_service.list_events(db, symbol)
        news_unavailable = len(any_events) == 0

    return StockEventListResponse(
        symbol=stock.symbol,
        category=category,
        count=len(events),
        events=[StockEventRead.model_validate(e) for e in events],
        news_unavailable=news_unavailable,
    )


@router.get("/{symbol}/events/{event_id}/impact", response_model=EventImpactResponse)
def get_event_impact(
    symbol: str,
    event_id: int,
    db: Session = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
) -> EventImpactResponse:
    """Post-event price-performance analysis across standard trading-session
    windows (1/5/20/60/120). This is historical observation only — not a
    recommendation, and not a claim that the event caused the movement.
    """
    event = event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Event {event_id} was not found."
        )

    symbol_upper = symbol.strip().upper()
    if event.stock.symbol != symbol_upper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id} does not belong to '{symbol_upper}'.",
        )

    result = compute_impact_for_event(db, service, event, symbol_upper)

    return EventImpactResponse(
        event_id=event.id,
        symbol=symbol_upper,
        event_date=event.published_at.date(),
        anchor_date=result.anchor_date,
        benchmark_symbol=DEFAULT_BENCHMARK_SYMBOL,
        benchmark_available=result.benchmark_available,
        windows=[
            EventImpactWindow(
                trading_days=w.trading_days,
                status=w.status,
                stock_return_pct=w.stock_return_pct,
                benchmark_return_pct=w.benchmark_return_pct,
                relative_return_pct=w.relative_return_pct,
                max_rise_pct=w.max_rise_pct,
                max_drawdown_pct=w.max_drawdown_pct,
            )
            for w in result.windows
        ],
        interpretation=build_interpretation(result.windows),
    )
