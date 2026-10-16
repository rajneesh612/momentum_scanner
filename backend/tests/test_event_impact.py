"""Tests for the pure post-event impact calculator (no FastAPI/DB)."""

from datetime import date, timedelta

import pytest

from app.momentum.event_impact import (
    WINDOW_TRADING_DAYS,
    build_interpretation,
    compute_event_impact,
)


def _series(start: date, closes: list[float]) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), c) for i, c in enumerate(closes)]


def test_all_windows_ok_with_sufficient_data_and_benchmark() -> None:
    start = date(2026, 1, 1)
    # 121 bars after (and including) the event date covers every window.
    stock = _series(start, [100.0 * (1 + 0.001 * i) for i in range(121)])
    benchmark = _series(start, [1000.0 * (1 + 0.0005 * i) for i in range(121)])

    result = compute_event_impact(
        stock, benchmark, event_date=start, today=start + timedelta(days=400)
    )

    assert result.anchor_date == start
    assert result.benchmark_available is True
    assert all(w.status == "ok" for w in result.windows)
    assert [w.trading_days for w in result.windows] == list(WINDOW_TRADING_DAYS)

    one_day = result.windows[0]
    expected_return = (stock[1][1] / stock[0][1] - 1) * 100
    assert one_day.stock_return_pct == pytest.approx(expected_return)
    assert one_day.relative_return_pct is not None


def test_event_day_itself_excluded_from_one_day_return() -> None:
    # Day 0 (anchor) close is the baseline, not part of the "return" - the
    # 1-trading-day window measures anchor -> anchor+1 only.
    start = date(2026, 1, 1)
    stock = [(start, 100.0), (start + timedelta(days=1), 110.0)]

    result = compute_event_impact(stock, [], event_date=start, today=start + timedelta(days=30))

    one_day = result.windows[0]
    assert one_day.status == "ok"
    assert one_day.stock_return_pct == pytest.approx(10.0)


def test_no_benchmark_data_marks_benchmark_fields_none() -> None:
    start = date(2026, 1, 1)
    stock = _series(start, [100.0 + i for i in range(10)])

    result = compute_event_impact(stock, [], event_date=start, today=start + timedelta(days=30))

    assert result.benchmark_available is False
    one_day = result.windows[0]
    assert one_day.status == "ok"
    assert one_day.stock_return_pct is not None
    assert one_day.benchmark_return_pct is None
    assert one_day.relative_return_pct is None


def test_window_too_recent_marked_pending_not_unavailable() -> None:
    start = date(2026, 1, 1)
    # Only 3 bars exist, and "today" is right after them - a 20-day window
    # can't exist yet in the real world either.
    stock = _series(start, [100.0, 101.0, 102.0])

    result = compute_event_impact(stock, [], event_date=start, today=start + timedelta(days=3))

    twenty_day = next(w for w in result.windows if w.trading_days == 20)
    assert twenty_day.status == "pending"
    assert twenty_day.stock_return_pct is None


def test_window_overdue_marked_unavailable_not_pending() -> None:
    start = date(2026, 1, 1)
    # Only 3 bars exist, but a year has passed - a 20-day window should
    # exist by now; its absence is "unavailable" (missing data), not
    # "pending" (not enough time passed).
    stock = _series(start, [100.0, 101.0, 102.0])

    result = compute_event_impact(stock, [], event_date=start, today=start + timedelta(days=365))

    twenty_day = next(w for w in result.windows if w.trading_days == 20)
    assert twenty_day.status == "unavailable"


def test_no_anchor_bar_marks_every_window_pending() -> None:
    # No bar on/after the event date exists at all yet.
    start = date(2026, 1, 1)
    stock: list[tuple[date, float]] = []

    result = compute_event_impact(stock, [], event_date=start, today=start)

    assert result.anchor_date is None
    assert all(w.status == "pending" for w in result.windows)


def test_max_rise_and_drawdown_within_window() -> None:
    start = date(2026, 1, 1)
    # Entry 100, then up to 120 (max rise +20%), down to 90 (max dd -10%).
    stock = [
        (start, 100.0),
        (start + timedelta(days=1), 120.0),
        (start + timedelta(days=2), 90.0),
    ]

    result = compute_event_impact(stock, [], event_date=start, today=start + timedelta(days=30))

    one_day = result.windows[0]
    two_day_closes = [c for _, c in stock]
    # trading_days=1 window only spans anchor..anchor+1 (100 -> 120).
    assert one_day.max_rise_pct == pytest.approx(20.0)
    assert one_day.max_drawdown_pct == pytest.approx(0.0)
    assert two_day_closes[-1] == 90.0  # sanity on fixture


def test_no_lookahead_future_bars_do_not_affect_earlier_windows() -> None:
    start = date(2026, 1, 1)
    closes_a = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    closes_b = [100.0, 101.0, 102.0, 103.0, 104.0, 9999.0]
    stock_a = _series(start, closes_a)
    stock_b = _series(start, closes_b)

    today = start + timedelta(days=30)
    result_a = compute_event_impact(stock_a, [], event_date=start, today=today)
    result_b = compute_event_impact(stock_b, [], event_date=start, today=today)

    # Window=1 only touches index 1 (differs), but windows that don't
    # reach the changed last bar must be identical between the two runs.
    for wa, wb in zip(result_a.windows, result_b.windows, strict=True):
        if wa.trading_days < 5:
            assert wa.stock_return_pct == pytest.approx(wb.stock_return_pct)


def test_build_interpretation_describes_rise_and_benchmark_comparison() -> None:
    start = date(2026, 1, 1)
    stock = _series(start, [100.0, 105.0])
    benchmark = _series(start, [1000.0, 1010.0])

    result = compute_event_impact(
        stock, benchmark, event_date=start, today=start + timedelta(days=30)
    )
    lines = build_interpretation(result.windows)

    assert any("rose" in line and "5.00%" in line for line in lines)
    assert any("percentage points above" in line for line in lines)


def test_build_interpretation_notes_reversal() -> None:
    start = date(2026, 1, 1)
    # 1-day window: +10%. 5-day window: ends down -5% from entry.
    closes = [100.0, 110.0, 108.0, 103.0, 98.0, 95.0]
    stock = _series(start, closes)

    result = compute_event_impact(stock, [], event_date=start, today=start + timedelta(days=30))
    lines = build_interpretation(result.windows)

    assert any("reversed" in line for line in lines)


def test_build_interpretation_handles_no_data_yet() -> None:
    lines = build_interpretation([])
    assert lines == [
        "Not enough trading-session data is available yet to describe the stock's "
        "behavior after this event."
    ]
