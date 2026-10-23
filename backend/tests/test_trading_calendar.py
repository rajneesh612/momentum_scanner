"""Tests for the weekday-based session-date helper."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.trading_calendar import latest_completed_session, previous_weekday

IST = ZoneInfo("Asia/Kolkata")


def test_previous_weekday_skips_weekend() -> None:
    # Monday 2024-01-08 -> previous weekday is Friday 2024-01-05.
    assert previous_weekday(date(2024, 1, 8)) == date(2024, 1, 5)


def test_latest_completed_session_before_close_delay_returns_previous_day() -> None:
    # Tuesday 2024-01-09, 10:00 IST - well before close+delay.
    now = datetime(2024, 1, 9, 10, 0, tzinfo=IST)
    assert latest_completed_session(now=now) == date(2024, 1, 8)


def test_latest_completed_session_after_close_delay_returns_today() -> None:
    # Tuesday 2024-01-09, 16:30 IST - after the default 15:30+45min window.
    now = datetime(2024, 1, 9, 16, 30, tzinfo=IST)
    assert latest_completed_session(now=now) == date(2024, 1, 9)


def test_latest_completed_session_on_weekend_returns_friday() -> None:
    # Saturday 2024-01-13, any time.
    now = datetime(2024, 1, 13, 20, 0, tzinfo=IST)
    assert latest_completed_session(now=now) == date(2024, 1, 12)
