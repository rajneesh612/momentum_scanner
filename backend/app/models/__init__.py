"""SQLAlchemy ORM models.

Importing this package registers all models on `Base.metadata`, which is
required for `Base.metadata.create_all()` (used by tests) and for future
Alembic autogeneration to see every table.
"""

from app.models.price_history import PriceHistory
from app.models.stock import Stock
from app.models.stock_event import StockEvent

__all__ = ["PriceHistory", "Stock", "StockEvent"]
