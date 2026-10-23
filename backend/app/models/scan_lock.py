"""ScanLock ORM model.

A trivial database-backed mutex: one row per named lock, with a unique
primary key on `name`. Acquiring the lock is an INSERT that either
succeeds (lock acquired) or violates the primary key (someone else holds
it) - this works the same way on SQLite (tests) and Postgres (prod), and
across multiple backend worker processes, without needing Postgres
advisory locks specifically. See `app/services/scan_lock_service.py`.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScanLock(Base):
    __tablename__ = "scan_locks"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_by: Mapped[str] = mapped_column(String(128), nullable=False)
