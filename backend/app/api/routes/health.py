"""Health/status API routes."""

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse, RootResponse

router = APIRouter(tags=["health"])


@router.get("/", response_model=RootResponse)
def read_root(settings: Settings = Depends(get_settings)) -> RootResponse:
    """Basic root endpoint confirming the API is reachable."""
    return RootResponse(message=f"{settings.app_name} API is running", docs_url="/docs")


@router.get("/health", response_model=HealthResponse)
def read_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness/health check endpoint."""
    return HealthResponse(status="ok", app_name=settings.app_name, app_env=settings.app_env)
