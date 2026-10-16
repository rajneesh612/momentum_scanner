"""Stock-related API routes."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_service
from app.core.database import get_db
from app.data.ingestion.provider import VALID_INTERVALS
from app.schemas.market_data import HistoricalPriceResponse
from app.schemas.price_history import PriceHistoryRead
from app.schemas.stock import StockListResponse, StockRead
from app.services import stock_service
from app.services.market_data_service import MarketDataService, StockNotFoundError

router = APIRouter(prefix="/stocks", tags=["stocks"])


@router.get("", response_model=StockListResponse)
def list_stocks(
    q: str | None = None,
    is_active: bool = True,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> StockListResponse:
    """Search/list the stock master (symbol + company name + exchange).

    Reads from the `Stock` table only — never calls Yahoo Finance. Used to
    populate a symbol picker. `q` matches against symbol or company name
    (case-insensitive substring). `is_active` defaults to True (only active
    stocks are returned); pass `is_active=false` to see inactive ones
    instead.
    """
    items, total = stock_service.list_stocks(
        db, q=q, is_active=is_active, limit=limit, offset=offset
    )
    return StockListResponse(
        items=[StockRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{symbol}/history", response_model=HistoricalPriceResponse)
def get_stock_history(
    symbol: str,
    start_date: date,
    end_date: date,
    interval: str = "1d",
    db: Session = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
) -> HistoricalPriceResponse:
    """Return previously-synced price history for a symbol at the given interval."""
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must not be after end_date.",
        )
    if interval not in VALID_INTERVALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"interval must be one of {sorted(VALID_INTERVALS)}.",
        )

    try:
        stock, prices = service.get_price_history(db, symbol, start_date, end_date, interval)
    except StockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not prices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No historical price data found for '{symbol}' "
                f"between {start_date} and {end_date}."
            ),
        )

    return HistoricalPriceResponse(
        symbol=stock.symbol,
        exchange=stock.exchange,
        interval=interval,
        start_date=start_date,
        end_date=end_date,
        count=len(prices),
        prices=[PriceHistoryRead.model_validate(price) for price in prices],
    )
