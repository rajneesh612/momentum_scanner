"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.backtest import router as backtest_router
from app.api.routes.events import router as events_router
from app.api.routes.health import router as health_router
from app.api.routes.market_data import router as market_data_router
from app.api.routes.stocks import router as stocks_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(stocks_router, prefix=settings.api_v1_prefix)
app.include_router(market_data_router, prefix=settings.api_v1_prefix)
app.include_router(backtest_router, prefix=settings.api_v1_prefix)
app.include_router(events_router, prefix=settings.api_v1_prefix)
