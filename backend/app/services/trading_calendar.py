"""Minimal weekday-based trading-session calendar.

Deliberately does not model NSE holidays - there is no holiday calendar
wired into this project. A scan that runs on an NSE holiday will simply
find no fresh bar for that date and report the symbol as `stale` (see
`app/momentum/hybrid_signal.py`), which is honest, just not as precise as
a real exchange calendar would be. This is disclosed as a known
limitation, not silently worked around.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def is_weekday(d: date) -> bool:
    return d.weekday() < 5  # Monday=0 ... Sunday=6


def previous_weekday(d: date) -> date:
    """The most recent Mon-Fri date strictly before `d`."""
    prev = d - timedelta(days=1)
    while not is_weekday(prev):
        prev -= timedelta(days=1)
    return prev


def latest_completed_session(
    timezone_name: str = "Asia/Kolkata",
    post_close_delay_minutes: int = 45,
    close_hour: int = 15,
    close_minute: int = 30,
    now: datetime | None = None,
) -> date:
    """The most recent trading session whose daily candle should be
    complete by now.

    On a weekday, before `close_hour:close_minute` + `post_close_delay_minutes`,
    today's own candle is still forming, so this returns the previous
    weekday. From that moment on, it returns today. On a weekend, it
    always returns the previous weekday regardless of time.
    """
    tz = ZoneInfo(timezone_name)
    now = now.astimezone(tz) if now is not None else datetime.now(tz)
    today = now.date()

    if not is_weekday(today):
        return previous_weekday(today)

    ready_at = datetime.combine(today, time(close_hour, close_minute), tzinfo=tz) + timedelta(
        minutes=post_close_delay_minutes
    )
    if now >= ready_at:
        return today
    return previous_weekday(today)
