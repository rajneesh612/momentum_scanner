"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings.

    Values are read from environment variables (or a local .env file in
    development). Nothing sensitive is hardcoded here — see .env.example
    for the variables this application expects.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Momentum Stock Scanner"
    app_env: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/momentum_stock_scanner"

    api_v1_prefix: str = "/api/v1"

    cors_origins: list[str] = ["http://localhost:5173"]

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Cached so environment variables are parsed once per process; use
    FastAPI's dependency injection (Depends(get_settings)) to access it.
    """
    return Settings()
