"""StrategyConfigVersion ORM model.

Records which parameter set was active at a point in time, mainly so a
future backtest/audit can answer "what thresholds produced this signal"
without reverse-engineering it from code history. The *authoritative*
config at scan time still comes from `HybridStrategyConfig` (code +
environment, see `app/services/signal_service.py`); this table is a
log of that config, not a live source of it, to avoid two sources of
truth for what the scanner actually runs with.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StrategyConfigVersion(Base):
    __tablename__ = "strategy_config_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    # Plain JSON-as-text, same rationale as SignalEvent.indicators_json.
    params_json: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
