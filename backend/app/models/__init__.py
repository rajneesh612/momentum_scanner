"""SQLAlchemy ORM models.

Importing this package registers all models on `Base.metadata`, which is
required for `Base.metadata.create_all()` (used by tests) and for future
Alembic autogeneration to see every table.
"""

from app.models.notification_delivery import NotificationDelivery
from app.models.price_history import PriceHistory
from app.models.scan_lock import ScanLock
from app.models.scan_run import ScanRun
from app.models.signal_event import SignalEvent
from app.models.stock import Stock
from app.models.stock_event import StockEvent
from app.models.strategy_config import StrategyConfigVersion
from app.models.universe_membership import UniverseMembershipEvent

__all__ = [
    "NotificationDelivery",
    "PriceHistory",
    "ScanLock",
    "ScanRun",
    "SignalEvent",
    "Stock",
    "StockEvent",
    "StrategyConfigVersion",
    "UniverseMembershipEvent",
]
