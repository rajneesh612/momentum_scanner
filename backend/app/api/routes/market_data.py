"""Market data ingestion API routes."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_service
from app.core.database import get_db
from app.data.ingestion.provider import (
    VALID_INTERVALS,
    MarketDataProviderError,
    NoDataFoundError,
    SymbolNotFoundError,
)
from app.schemas.market_data import MarketDataSyncResponse
from app.services.market_data_service import MarketDataPersistenceError, MarketDataService

router = APIRouter(prefix="/market-data", tags=["market-data"])

_DEFAULT_SYNC_WINDOW_DAYS = 365


@router.post("/sync/{symbol}", response_model=MarketDataSyncResponse)
def sync_symbol_history(
    symbol: str,
    start_date: date | None = None,
    end_date: date | None = None,
    interval: str = "1d",
    db: Session = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
) -> MarketDataSyncResponse:
    """Fetch historical prices for a symbol and persist them.

    If start_date/end_date are omitted, defaults to the last 365 days.
    `interval` is one of "1d" (daily, default), "1wk" (weekly), "1mo"
    (monthly) — useful for syncing many years of history compactly.
    """
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=_DEFAULT_SYNC_WINDOW_DAYS))

    if start > end:
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
        result = service.sync_symbol_history(db, symbol, start, end, interval)
    except SymbolNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoDataFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except MarketDataPersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return MarketDataSyncResponse(
        symbol=result.symbol,
        interval=result.interval,
        start_date=result.start_date,
        end_date=result.end_date,
        records_fetched=result.records_fetched,
        records_created=result.records_created,
        records_skipped=result.records_skipped,
    )
