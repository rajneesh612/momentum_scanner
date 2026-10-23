"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to this file's own location (backend/app/core/config.py ->
# backend/.env), not to the process's current working directory.
# pydantic-settings resolves a *relative* env_file path against whatever
# directory the process happened to be launched from - if uvicorn is ever
# started from somewhere other than backend/ (a different terminal, an
# IDE's integrated terminal defaulting to the repo root, ...), a relative
# ".env" silently fails to resolve. pydantic-settings does not error on a
# missing env file; it just falls back to field defaults, so this would
# fail silently - a real .env with real values sitting right there,
# simply never read. Resolving to an absolute path here makes loading
# independent of launch directory.
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """Central application settings.

    Values are read from environment variables (or a local .env file in
    development). Nothing sensitive is hardcoded here — see .env.example
    for the variables this application expects.
    """

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
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

    # --- Telegram alerts ---
    # Never hardcode real values - see backend/.env.example.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_alerts_enabled: bool = False
    # Safety valve against an accidental storm of messages (e.g. a bad
    # threshold change flagging half the universe at once).
    telegram_max_notifications_per_scan: int = 20

    # --- Daily scanner scheduling ---
    scheduler_enabled: bool = False
    scheduler_timezone: str = "Asia/Kolkata"
    # NSE's cash session closes at 15:30 IST. The scan is scheduled this
    # many minutes after that, not exactly at close, since a bar isn't
    # reliably "completed" in the data provider the instant the bell
    # rings.
    scan_post_close_delay_minutes: int = 45
    scan_hour_ist: int = 16
    scan_minute_ist: int = 15

    # --- Manual-trigger / test endpoints ---
    # Empty disables these endpoints entirely (returns 401) - this must
    # be explicitly set to use POST /scans/run or /telegram/test.
    scan_api_key: str = ""

    # --- Scan concurrency/retry ---
    scan_max_concurrent_symbols: int = 5
    scan_max_retries: int = 3
    scan_retry_backoff_seconds: float = 2.0

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
