"""Daily hybrid-signal scanner API routes: signals, scan runs, manual
trigger, Telegram test, strategy config, universe refresh, and the
hybrid-strategy backtester."""

from __future__ import annotations

import contextlib
from datetime import date, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_market_data_provider, get_market_data_service, require_scan_api_key
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.data.ingestion.provider import MarketDataProvider, MarketDataProviderError
from app.models.scan_run import ScanRun
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.momentum.hybrid_signal import HybridStrategyConfig, run_hybrid_backtest
from app.schemas.backtest import BacktestTrade
from app.schemas.signal import (
    HybridBacktestResponse,
    HybridBacktestSummary,
    HybridEquityPointRead,
    ManualScanResponse,
    ScanRunListResponse,
    ScanRunRead,
    SignalEventListResponse,
    SignalEventRead,
    StrategyConfigResponse,
    SymbolScanOutcomeRead,
    TelegramTestResponse,
    UniverseRefreshResponse,
)
from app.services import scan_lock_service, scan_service, telegram_service, universe_service
from app.services.market_data_service import (
    MarketDataPersistenceError,
    MarketDataService,
    StockNotFoundError,
)
from app.services.trading_calendar import latest_completed_session

router = APIRouter(tags=["signals"])

DEFAULT_CONFIG = HybridStrategyConfig()


@router.get("/strategy-config", response_model=StrategyConfigResponse)
def get_strategy_config() -> StrategyConfigResponse:
    """The hybrid strategy's current parameters - informational only,
    never a place to change them (edit `HybridStrategyConfig` defaults or
    wire new env vars if that's needed)."""
    return StrategyConfigResponse(**DEFAULT_CONFIG.__dict__)


@router.get("/signals/latest", response_model=SignalEventListResponse)
def latest_signals(limit: int = 50, db: Session = Depends(get_db)) -> SignalEventListResponse:
    limit = max(1, min(limit, 200))
    rows = db.scalars(
        select(SignalEvent)
        .order_by(SignalEvent.session_date.desc(), SignalEvent.id.desc())
        .limit(limit)
    ).all()
    return SignalEventListResponse(
        items=[_signal_read(r) for r in rows], total=len(rows), limit=limit, offset=0
    )


@router.get("/signals", response_model=SignalEventListResponse)
def list_signals(
    symbol: str | None = None,
    signal_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> SignalEventListResponse:
    limit = max(1, min(limit, 200))
    filters = []
    if symbol:
        stock = db.scalar(select(Stock).where(Stock.symbol == symbol.strip().upper()))
        if stock is None:
            return SignalEventListResponse(items=[], total=0, limit=limit, offset=offset)
        filters.append(SignalEvent.stock_id == stock.id)
    if signal_type:
        filters.append(SignalEvent.signal_type == signal_type.upper())
    if start_date:
        filters.append(SignalEvent.session_date >= start_date)
    if end_date:
        filters.append(SignalEvent.session_date <= end_date)

    total = db.scalar(select(func.count()).select_from(SignalEvent).where(*filters)) or 0
    rows = db.scalars(
        select(SignalEvent)
        .where(*filters)
        .order_by(SignalEvent.session_date.desc(), SignalEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return SignalEventListResponse(
        items=[_signal_read(r) for r in rows], total=total, limit=limit, offset=offset
    )


def _signal_read(event: SignalEvent) -> SignalEventRead:
    data = SignalEventRead.model_validate(event)
    data.symbol = event.stock.symbol
    return data


@router.get("/scans/latest", response_model=ScanRunRead)
def latest_scan(db: Session = Depends(get_db)) -> ScanRunRead:
    run = db.scalar(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No scan has run yet.")
    return ScanRunRead.model_validate(run)


@router.get("/scans", response_model=ScanRunListResponse)
def list_scans(
    limit: int = 20, offset: int = 0, db: Session = Depends(get_db)
) -> ScanRunListResponse:
    limit = max(1, min(limit, 100))
    total = db.scalar(select(func.count()).select_from(ScanRun)) or 0
    rows = db.scalars(
        select(ScanRun).order_by(ScanRun.started_at.desc()).limit(limit).offset(offset)
    ).all()
    return ScanRunListResponse(
        items=[ScanRunRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/scans/run",
    response_model=ManualScanResponse,
    dependencies=[Depends(require_scan_api_key)],
)
def trigger_manual_scan(
    session_date: date | None = None,
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_market_data_provider),
    settings: Settings = Depends(get_settings),
) -> ManualScanResponse:
    """Run a full-universe scan right now - for troubleshooting, not a
    replacement for the schedule. Requires `X-Scan-Api-Key`."""
    resolved_session_date = session_date or latest_completed_session(
        timezone_name=settings.scheduler_timezone,
        post_close_delay_minutes=settings.scan_post_close_delay_minutes,
    )

    try:
        summary = scan_service.run_scan(
            db,
            provider,
            resolved_session_date,
            config=DEFAULT_CONFIG,
            trigger="manual",
            max_concurrent_symbols=settings.scan_max_concurrent_symbols,
            max_retries=settings.scan_max_retries,
            backoff_seconds=settings.scan_retry_backoff_seconds,
            max_notifications=settings.telegram_max_notifications_per_scan,
        )
    except scan_lock_service.ScanLockHeldError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ManualScanResponse(
        scan_run_id=summary.scan_run_id,
        status=summary.status,
        session_date=summary.session_date,
        universe_size=summary.universe_size,
        symbols_succeeded=summary.symbols_succeeded,
        symbols_failed=summary.symbols_failed,
        symbols_stale=summary.symbols_stale,
        symbols_skipped=summary.symbols_skipped,
        buy_signals=summary.buy_signals,
        sell_signals=summary.sell_signals,
        notifications_sent=summary.notifications_sent,
        notifications_failed=summary.notifications_failed,
        notifications_skipped_cap=summary.notifications_skipped_cap,
        error_message=summary.error_message,
        data_quality_report=[
            SymbolScanOutcomeRead(
                symbol=o.symbol,
                status=o.status,
                signal_type=o.signal_type,
                data_quality=o.data_quality,
                error=o.error,
            )
            for o in summary.outcomes
        ],
    )


@router.post(
    "/telegram/test",
    response_model=TelegramTestResponse,
    dependencies=[Depends(require_scan_api_key)],
)
def send_telegram_test() -> TelegramTestResponse:
    """Sends a plain test message - never a fabricated BUY/SELL signal.
    Requires `X-Scan-Api-Key`."""
    result = telegram_service.send_message(
        "✅ Momentum Stock Scanner: this is a test notification. "
        "If you can read this, Telegram alerts are configured correctly."
    )
    return TelegramTestResponse(success=result.success, error=result.error)


@router.post(
    "/universe/refresh",
    response_model=UniverseRefreshResponse,
    dependencies=[Depends(require_scan_api_key)],
)
def refresh_universe(db: Session = Depends(get_db)) -> UniverseRefreshResponse:
    """Refreshes the NIFTY 500 universe from NSE - a separate operation
    from scanning. On fetch failure, the existing universe is left
    completely untouched. Requires `X-Scan-Api-Key`."""
    result = universe_service.refresh_universe(db)
    return UniverseRefreshResponse(**result.__dict__)


@router.post("/backtest/hybrid/{symbol}", response_model=HybridBacktestResponse)
def backtest_hybrid_symbol(
    symbol: str,
    start_date: date,
    end_date: date,
    initial_capital: float = 100_000.0,
    cost_bps: float = 10.0,
    db: Session = Depends(get_db),
    service: MarketDataService = Depends(get_market_data_service),
) -> HybridBacktestResponse:
    """Backtests the exact same hybrid strategy the live scanner uses
    (see `app/momentum/hybrid_signal.py`), against previously-synced
    prices only - sync the symbol first via `POST /market-data/sync/{symbol}`."""
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must not be after end_date."
        )
    if initial_capital <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="initial_capital must be positive."
        )
    if cost_bps < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cost_bps must not be negative."
        )

    config = DEFAULT_CONFIG
    days_per_bar = 1.6
    lookback_start = start_date - timedelta(days=int(config.min_bars_required * days_per_bar) + 15)

    with contextlib.suppress(MarketDataProviderError, MarketDataPersistenceError):
        service.sync_symbol_history(db, symbol, lookback_start, end_date, "1d")

    try:
        stock, prices = service.get_price_history(db, symbol, lookback_start, end_date, "1d")
    except StockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    has_data_in_window = any(start_date <= p.date <= end_date for p in prices)
    if not has_data_in_window:
        detail = (
            f"No historical price data found for '{symbol}' between {start_date} and {end_date}."
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    df = pd.DataFrame(
        {
            "date": [p.date for p in prices],
            "close": [p.adjusted_close for p in prices],
            "volume": [p.volume for p in prices],
        }
    )

    result = run_hybrid_backtest(df, config, start_date, end_date, initial_capital, cost_bps)

    return HybridBacktestResponse(
        symbol=stock.symbol,
        exchange=stock.exchange,
        strategy=config.name,
        start_date=start_date,
        end_date=end_date,
        lookback_bars=result.lookback_bars,
        warmup_complete_date=result.warmup_complete_date,
        is_fully_warmed_up=result.is_fully_warmed_up,
        cost_model=(
            f"{cost_bps:.1f} bps round-trip cost, next-session-close execution (no look-ahead)."
        ),
        summary=HybridBacktestSummary(
            initial_capital=result.initial_capital,
            final_equity=result.final_equity,
            total_return_pct=result.total_return_pct,
            buy_and_hold_return_pct=result.buy_and_hold_return_pct,
            cagr_pct=result.cagr_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            volatility_pct_annualized=result.volatility_pct_annualized,
            sharpe_ratio=result.sharpe_ratio,
            num_trades=len(result.closed_trades),
            win_rate_pct=result.win_rate_pct,
            avg_trade_return_pct=result.avg_trade_return_pct,
            exposure_pct=result.exposure_pct,
            turnover=result.turnover,
            cost_bps=cost_bps,
        ),
        equity_curve=[
            HybridEquityPointRead(
                date=p.date,
                close=p.close,
                equity=p.equity,
                in_position=p.in_position,
                data_quality=p.data_quality,
                sma_mid=p.sma_mid,
                sma_long=p.sma_long,
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
