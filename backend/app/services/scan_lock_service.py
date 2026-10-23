"""Database-backed mutex so two backend workers never run the daily scan
at the same time.

Works by racing an INSERT against `ScanLock.name`'s primary key: exactly
one concurrent caller wins. A stale lock (the process that held it died
without releasing it - crash, OOM kill, etc.) is reclaimed after
`stale_after_minutes`, so a dead worker can never permanently wedge
scanning.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.scan_lock import ScanLock

DEFAULT_LOCK_NAME = "daily_signal_scan"


class ScanLockHeldError(Exception):
    """Raised when the lock is already held by another (non-stale) run."""


@dataclass
class LockHandle:
    name: str
    token: str


def try_acquire(
    db: Session, name: str = DEFAULT_LOCK_NAME, stale_after_minutes: int = 30
) -> LockHandle:
    """Acquire the named lock or raise ScanLockHeldError.

    Reclaims a stale lock (older than `stale_after_minutes`) first, as a
    separate committed step, so a crashed worker's lock cannot block
    scanning forever.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=stale_after_minutes)
    existing = db.scalar(select(ScanLock).where(ScanLock.name == name))
    # SQLite (used in tests) does not round-trip timezone info on a
    # DateTime(timezone=True) column - it comes back naive, even though
    # it was always written as UTC (server_default=func.now()). Postgres
    # (prod) returns it already tz-aware. Normalize both to aware-UTC
    # before comparing, rather than letting this differ by database.
    locked_at = existing.locked_at if existing is not None else None
    if locked_at is not None and locked_at.tzinfo is None:
        locked_at = locked_at.replace(tzinfo=UTC)
    if existing is not None and locked_at < cutoff:
        db.execute(delete(ScanLock).where(ScanLock.name == name))
        db.commit()

    token = uuid4().hex
    db.add(ScanLock(name=name, locked_by=token))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ScanLockHeldError(f"Scan lock '{name}' is already held.") from exc

    return LockHandle(name=name, token=token)


def release(db: Session, handle: LockHandle) -> None:
    """Release the lock, but only if we still hold it (token matches) -
    never release a lock some other, newer run has since acquired after
    reclaiming a stale one."""
    db.execute(
        delete(ScanLock).where(ScanLock.name == handle.name, ScanLock.locked_by == handle.token)
    )
    db.commit()


@contextmanager
def scan_lock(db: Session, name: str = DEFAULT_LOCK_NAME, stale_after_minutes: int = 30):
    handle = try_acquire(db, name, stale_after_minutes)
    try:
        yield handle
    finally:
        release(db, handle)
