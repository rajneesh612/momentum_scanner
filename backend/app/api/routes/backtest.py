"""Momentum strategy backtesting API routes."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_service
from app.core.database import get_db
from app.data.ingestion.provider import VALID_INTERVALS
from app.schemas.backtest import BacktestResponse, BacktestSummary, BacktestTrade, EquityPoint
from app.services.backtest_service import NoBacktestDataError, run_backtest
from app.services.market_data_service import MarketDataService, StockNotFoundError

router = APIRouter(prefix="/backtest", tags=["backtest"])

_DEFAULT_SHORT_WINDOW = 50
_DEFAULT_LONG_WINDOW = 200
_DEFAULT_INITIAL_CAPITAL = 100_000.0


@router.post("/{symbol}", response_model=BacktestResponse)
def backtest_symbol(
    symbol: str,
    start_date: date,
    end_date: date,
    short_window: int = _DEFAULT_SHORT_WINDOW,
    long_window: int = _DEFAULT_LONG_WINDOW,
    initial_capital: float = _DEFAULT_INITIAL_CAPITAL,
    interval: str = "1d",
    db: Session = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
) -> BacktestResponse:
    """Run a long-only SMA-crossover backtest against previously-synced prices.

    Reads from PriceHistory only — it never calls the market data provider,
    so the symbol's history must already be synced via
    `POST /market-data/sync/{symbol}` first.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must not be after end_date.",
        )
    if short_window <= 0 or long_window <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="short_window and long_window must be positive.",
        )
    if short_window >= long_window:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="short_window must be less than long_window.",
        )
    if initial_capital <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="initial_capital must be positive.",
        )
    if interval not in VALID_INTERVALS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"interval must be one of {sorted(VALID_INTERVALS)}.",
        )

    try:
        stock, result = run_backtest(
            db,
            service,
            symbol,
            start_date,
            end_date,
            short_window,
            long_window,
            initial_capital,
            interval,
        )
    except StockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except NoBacktestDataError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return BacktestResponse(
        symbol=stock.symbol,
        exchange=stock.exchange,
        strategy="sma_crossover",
        interval=interval,
        short_window=short_window,
        long_window=long_window,
        start_date=start_date,
        end_date=end_date,
        lookback_bars=result.lookback_bars,
        warmup_complete_date=result.warmup_complete_date,
        is_fully_warmed_up=result.is_fully_warmed_up,
        summary=BacktestSummary(
            initial_capital=result.initial_capital,
            final_equity=result.final_equity,
            total_return_pct=result.total_return_pct,
            buy_and_hold_return_pct=result.buy_and_hold_return_pct,
            cagr_pct=result.cagr_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            num_trades=len(result.closed_trades),
            win_rate_pct=result.win_rate_pct,
        ),
        equity_curve=[
            EquityPoint(
                date=p.date,
                close=p.close,
                equity=p.equity,
                in_position=p.in_position,
                short_sma=p.short_sma,
                long_sma=p.long_sma,
            )
            for p in result.equity_curve
        ],
        trades=[
            BacktestTrade(
                entry_date=t.entry_date,
                entry_price=t.entry_price,
                exit_date=t.exit_date,
                exit_price=t.exit_price,
                return_pct=t.return_pct,
                holding_days=t.holding_days,
                is_open=t.is_open,
            )
            for t in result.trades
        ],
    )
