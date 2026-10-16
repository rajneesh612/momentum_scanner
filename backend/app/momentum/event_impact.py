"""Post-event price-impact calculator.

Pure functions operating on plain (date, close) price series — no
FastAPI/DB dependency, same pattern as `app/momentum/backtest.py`.
`app/services/event_impact_service.py` is the only place that bridges
this to persisted PriceHistory/StockEvent rows.

Definitions (documented, not silently assumed):
- "Day 0" (the anchor) is the first trading session on/after the event's
  published date. Its close is the baseline price.
- A window's return is measured from Day 0's close to the close N trading
  sessions later — the event day's own move is the baseline, not counted
  as part of the "return"; "1 trading day" means the very next session.
- Every window only ever reads bars at/after Day 0 — never bars from
  before the event — so no window can leak pre-event information forward,
  and no later window's data can leak into an earlier one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

WINDOW_TRADING_DAYS: tuple[int, ...] = (1, 5, 20, 60, 120)

# Rough calendar days per trading session, used only to tell "pending"
# (not enough real-world time has passed yet) apart from "unavailable"
# (enough time has passed but the bars are still missing).
_CALENDAR_DAYS_PER_TRADING_DAY = 1.6
_PENDING_SLACK_DAYS = 5


@dataclass
class WindowResult:
    trading_days: int
    status: str  # "ok" | "pending" | "unavailable"
    stock_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    relative_return_pct: float | None = None
    max_rise_pct: float | None = None
    max_drawdown_pct: float | None = None


@dataclass
class EventImpactResult:
    anchor_date: date | None
    benchmark_available: bool
    windows: list[WindowResult] = field(default_factory=list)


def _find_anchor_index(dates: list[date], event_date: date) -> int | None:
    for i, d in enumerate(dates):
        if d >= event_date:
            return i
    return None


def _window_extrema(closes: list[float], entry: float) -> tuple[float, float]:
    moves = [(c - entry) / entry * 100 for c in closes]
    return max(moves), min(moves)


def compute_event_impact(
    stock_series: list[tuple[date, float]],
    benchmark_series: list[tuple[date, float]],
    event_date: date,
    today: date,
) -> EventImpactResult:
    """`stock_series`/`benchmark_series` must be sorted ascending by date."""
    stock_dates = [d for d, _ in stock_series]
    stock_closes = [c for _, c in stock_series]
    benchmark_available = len(benchmark_series) > 0
    bench_dates = [d for d, _ in benchmark_series]
    bench_closes = [c for _, c in benchmark_series]

    anchor_idx = _find_anchor_index(stock_dates, event_date)
    bench_anchor_idx = _find_anchor_index(bench_dates, event_date) if benchmark_available else None

    if anchor_idx is None:
        windows = [WindowResult(trading_days=n, status="pending") for n in WINDOW_TRADING_DAYS]
        return EventImpactResult(
            anchor_date=None, benchmark_available=benchmark_available, windows=windows
        )

    anchor_date = stock_dates[anchor_idx]
    entry_price = stock_closes[anchor_idx]
    bench_entry_price = bench_closes[bench_anchor_idx] if bench_anchor_idx is not None else None

    windows: list[WindowResult] = []
    for n in WINDOW_TRADING_DAYS:
        exit_idx = anchor_idx + n
        if exit_idx >= len(stock_closes) or entry_price <= 0:
            required_days = int(n * _CALENDAR_DAYS_PER_TRADING_DAY) + _PENDING_SLACK_DAYS
            is_pending = (today - anchor_date).days < required_days
            status = "pending" if is_pending else "unavailable"
            windows.append(WindowResult(trading_days=n, status=status))
            continue

        exit_price = stock_closes[exit_idx]
        stock_return = (exit_price / entry_price - 1) * 100
        max_rise, max_dd = _window_extrema(stock_closes[anchor_idx : exit_idx + 1], entry_price)

        benchmark_return = None
        relative_return = None
        if bench_anchor_idx is not None and bench_entry_price and bench_entry_price > 0:
            bench_exit_idx = bench_anchor_idx + n
            if bench_exit_idx < len(bench_closes):
                benchmark_return = (bench_closes[bench_exit_idx] / bench_entry_price - 1) * 100
                relative_return = stock_return - benchmark_return

        windows.append(
            WindowResult(
                trading_days=n,
                status="ok",
                stock_return_pct=stock_return,
                benchmark_return_pct=benchmark_return,
                relative_return_pct=relative_return,
                max_rise_pct=max_rise,
                max_drawdown_pct=max_dd,
            )
        )

    return EventImpactResult(
        anchor_date=anchor_date, benchmark_available=benchmark_available, windows=windows
    )


def build_interpretation(windows: list[WindowResult]) -> list[str]:
    """Neutral, metrics-derived sentences describing observed price
    behavior after the event. Never asserts causation and never predicts
    what happens next — only describes what the computed windows show.
    """
    ok_windows = [w for w in windows if w.status == "ok" and w.stock_return_pct is not None]
    lines: list[str] = []

    for w in ok_windows:
        direction = "rose" if w.stock_return_pct >= 0 else "fell"
        plural = "" if w.trading_days == 1 else "s"
        line = (
            f"The stock {direction} {abs(w.stock_return_pct):.2f}% over the next "
            f"{w.trading_days} trading session{plural}."
        )
        if w.relative_return_pct is not None:
            rel_direction = "above" if w.relative_return_pct >= 0 else "below"
            line += (
                f" That's {abs(w.relative_return_pct):.2f} percentage points {rel_direction} "
                "the NIFTY 50 benchmark over the same period."
            )
        lines.append(line)

    if len(ok_windows) >= 2:
        first, last = ok_windows[0], ok_windows[-1]
        if first.stock_return_pct is not None and last.stock_return_pct is not None:
            if first.stock_return_pct > 0 and last.stock_return_pct < 0:
                lines.append(
                    f"The initial rise after {first.trading_days} session(s) had reversed by "
                    f"the {last.trading_days}-session window."
                )
            elif first.stock_return_pct < 0 and last.stock_return_pct > 0:
                lines.append(
                    f"The initial decline after {first.trading_days} session(s) had reversed "
                    f"by the {last.trading_days}-session window."
                )

    if not ok_windows:
        lines.append(
            "Not enough trading-session data is available yet to describe the stock's "
            "behavior after this event."
        )

    return lines
