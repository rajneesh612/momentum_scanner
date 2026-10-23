"""Tests for the DB-backed scan mutex."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.scan_lock import ScanLock
from app.services import scan_lock_service


def test_acquire_and_release(db_session: Session) -> None:
    handle = scan_lock_service.try_acquire(db_session)
    assert db_session.get(ScanLock, handle.name) is not None

    scan_lock_service.release(db_session, handle)
    assert db_session.get(ScanLock, handle.name) is None


def test_second_acquire_while_held_raises(db_session: Session) -> None:
    handle = scan_lock_service.try_acquire(db_session)
    try:
        import pytest

        with pytest.raises(scan_lock_service.ScanLockHeldError):
            scan_lock_service.try_acquire(db_session)
    finally:
        scan_lock_service.release(db_session, handle)


def test_stale_lock_is_reclaimed(db_session: Session) -> None:
    handle = scan_lock_service.try_acquire(db_session)
    lock = db_session.get(ScanLock, handle.name)
    assert lock is not None
    lock.locked_at = lock.locked_at - timedelta(minutes=60)
    db_session.commit()

    # Within the default 30-minute staleness window this would raise -
    # since it's 60 minutes old, it must be reclaimable instead.
    new_handle = scan_lock_service.try_acquire(db_session, stale_after_minutes=30)
    assert new_handle.token != handle.token
    scan_lock_service.release(db_session, new_handle)


def test_release_only_releases_own_token(db_session: Session) -> None:
    handle = scan_lock_service.try_acquire(db_session)
    other_handle = scan_lock_service.LockHandle(name=handle.name, token="not-the-real-token")

    scan_lock_service.release(db_session, other_handle)

    # The real lock must still be held.
    assert db_session.get(ScanLock, handle.name) is not None
    scan_lock_service.release(db_session, handle)


def test_scan_lock_context_manager_always_releases(db_session: Session) -> None:
    with scan_lock_service.scan_lock(db_session) as handle:
        assert db_session.get(ScanLock, handle.name) is not None
    assert db_session.get(ScanLock, handle.name) is None
