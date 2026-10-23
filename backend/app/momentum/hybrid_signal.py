"""Hybrid trend/momentum/volume daily signal engine.

Pure dataclasses/functions operating on a plain price DataFrame - no
FastAPI, database, or scheduling dependency, so this stays independently
testable and is reusable by both the live daily scanner
(`app/services/signal_service.py`) and the backtester below. The same
`evaluate_series`/`_is_eligible`/`_is_exit` logic drives both, so a
backtest result reflects exactly what the live scanner would have done.

Adjusted-price policy: every price-based indicator here (SMA, momentum)
is computed from `adjusted_close`, never from raw/unadjusted OHLC, so a
stock split or bonus issue cannot masquerade as a crash or a rally. There
is a deliberate deviation from "ATR" as commonly defined: true ATR needs
split-adjusted high/low, which this project's PriceHistory table does not
store (only `adjusted_close` is adjusted). Mixing an adjusted close with
unadjusted high/low would be internally inconsistent, so `volatility_pct`
below is a rolling stdev of adjusted-close daily returns instead - a
volatility proxy, not true ATR. It is informational only and never feeds
into eligibility/exit rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app.momentum.backtest import Trade

# Signal event type strings - shared with the DB model's `signal_type` column.
BUY = "BUY"
SELL = "SELL"

# Data-quality status strings - shared with the DB model's
# `data_quality_status` column.
DQ_OK = "ok"
DQ_INSUFFICIENT = "insufficient"
DQ_STALE = "stale"
DQ_MISSING = "missing"


@dataclass(frozen=True)
class HybridStrategyConfig:
    """All tunable parameters for the hybrid strategy, in one place.

    `name`/`version` identify this configuration for persistence (a
    SignalEvent records which strategy name+version produced it, so
    changing a threshold later doesn't retroactively reinterpret old
    signals) and for Telegram message text.
    """

    name: str = "hybrid_daily"
    version: str = "v1"

    sma_short: int = 20
    sma_mid: int = 50
    sma_long: int = 200

    momentum_short_days: int = 20
    # ~12 months of trading sessions (NSE: ~250/year). Deliberately a
    # session count, not a calendar-day count, so it is unaffected by
    # weekends/holidays.
    momentum_long_days: int = 252

    volume_lookback: int = 20
    volume_multiplier: float = 1.2

    volatility_lookback: int = 14

    # A completed session's data is considered stale (not usable to
    # generate a fresh signal) if the latest available bar is older than
    # this many calendar days relative to the session date being
    # evaluated. Generous enough to tolerate a single NSE holiday cluster
    # without false "stale" flags, tight enough to catch a genuinely dead
    # feed.
    max_staleness_days: int = 5

    @property
    def min_bars_required(self) -> int:
        """Bars (rows) needed before indicators are fully defined.

        +1 on the momentum windows because an N-session return needs the
        close N sessions ago *and* today's close (N+1 data points).
        """
        return max(self.sma_long, self.momentum_long_days + 1)


@dataclass
class HybridEvaluation:
    """The result of evaluating one completed session for one stock."""

    date: date
    close: float
    volume: float
    data_quality: str
    eligible: bool
    exit_triggered: bool
    in_position_before: bool
    in_position_after: bool
    signal: str | None
    indicators: dict[str, float | None]


def compute_indicators(df: pd.DataFrame, config: HybridStrategyConfig) -> pd.DataFrame:
    """Add indicator columns to a (date, close, volume) price DataFrame.

    `close` is expected to already be the adjusted close - callers (e.g.
    `signal_service`) are responsible for passing `PriceHistory.adjusted_close`
    here, never the raw `close`.
    """
    out = df.sort_values("date").reset_index(drop=True).copy()
    out["sma_short"] = out["close"].rolling(window=config.sma_short).mean()
    out["sma_mid"] = out["close"].rolling(window=config.sma_mid).mean()
    out["sma_long"] = out["close"].rolling(window=config.sma_long).mean()
    out["volume_avg"] = out["volume"].rolling(window=config.volume_lookback).mean()
    out["momentum_short_pct"] = (
        out["close"] / out["close"].shift(config.momentum_short_days) - 1
    ) * 100
    out["momentum_long_pct"] = (
        out["close"] / out["close"].shift(config.momentum_long_days) - 1
    ) * 100
    daily_returns = out["close"].pct_change()
    out["volatility_pct"] = (
        daily_returns.rolling(window=config.volatility_lookback).std() * 100
    )
    return out


def _row_data_quality(
    row: pd.Series, config: HybridStrategyConfig, bar_index: int, session_date: date
) -> str:
    """Classify one row's usability for generating a signal.

    `bar_index` is the row's 0-based position in the full (sorted)
    history fed to `compute_indicators` - used to check enough prior bars
    exist, independent of calendar gaps.
    """
    if bar_index + 1 < config.min_bars_required:
        return DQ_INSUFFICIENT
    if pd.isna(row["close"]) or pd.isna(row["volume"]) or row["volume"] <= 0:
        return DQ_INSUFFICIENT
    if any(pd.isna(row[c]) for c in ("sma_short", "sma_mid", "sma_long", "volume_avg")):
        return DQ_INSUFFICIENT
    if pd.isna(row["momentum_short_pct"]) or pd.isna(row["momentum_long_pct"]):
        return DQ_INSUFFICIENT
    staleness_days = (session_date - row["date"]).days
    if staleness_days > config.max_staleness_days:
        return DQ_STALE
    return DQ_OK


def _is_eligible(row: pd.Series, config: HybridStrategyConfig) -> bool:
    """The initial BUY-eligibility conditions (section 5, rules 1-5).

    Rule 6 (data-quality gate) is enforced by the caller via
    `_row_data_quality` before this is ever called.
    """
    return bool(
        row["close"] > row["sma_mid"]
        and row["sma_mid"] > row["sma_long"]
        and row["momentum_short_pct"] > 0
        and row["momentum_long_pct"] > 0
        and row["volume"] > row["volume_avg"] * config.volume_multiplier
    )


def _is_exit(row: pd.Series) -> bool:
    """The exit/SELL conditions: close below SMA-mid, or SMA-mid below SMA-long."""
    return bool(row["close"] < row["sma_mid"] or row["sma_mid"] < row["sma_long"])


def _indicator_snapshot(row: pd.Series) -> dict[str, float | None]:
    def _val(key: str) -> float | None:
        value = row[key]
        return None if pd.isna(value) else float(value)

    return {
        "sma_short": _val("sma_short"),
        "sma_mid": _val("sma_mid"),
        "sma_long": _val("sma_long"),
        "volume_avg": _val("volume_avg"),
        "momentum_short_pct": _val("momentum_short_pct"),
        "momentum_long_pct": _val("momentum_long_pct"),
        "volatility_pct": _val("volatility_pct"),
    }


def evaluate_series(
    df: pd.DataFrame,
    config: HybridStrategyConfig,
    in_position_start: bool = False,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[HybridEvaluation]:
    """Walk a full price series and replay BUY/SELL/HOLD state transitions.

    `df` may (and for correct warmup, should) include rows before
    `start_date` - they are used to compute indicators but never emitted.
    `in_position_start` lets a caller resume an already-open position at
    the start of the window (used by the live scanner, which reads the
    persisted state rather than always starting flat).
    """
    indicators = compute_indicators(df, config)
    in_position = in_position_start
    results: list[HybridEvaluation] = []

    for idx, row in indicators.iterrows():
        row_date = row["date"]
        if start_date is not None and row_date < start_date:
            continue
        if end_date is not None and row_date > end_date:
            break

        dq = _row_data_quality(row, config, idx, row_date)
        eligible = dq == DQ_OK and _is_eligible(row, config)
        exit_triggered = dq == DQ_OK and in_position and _is_exit(row)

        signal: str | None = None
        in_position_before = in_position
        if not in_position and eligible:
            signal = BUY
            in_position = True
        elif in_position and exit_triggered:
            signal = SELL
            in_position = False

        results.append(
            HybridEvaluation(
                date=row_date,
                close=float(row["close"]),
                volume=float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
                data_quality=dq,
                eligible=eligible,
                exit_triggered=exit_triggered,
                in_position_before=in_position_before,
                in_position_after=in_position,
                signal=signal,
                indicators=_indicator_snapshot(row),
            )
        )

    return results


def _missing_evaluation(session_date: date, in_position: bool) -> HybridEvaluation:
    return HybridEvaluation(
        date=session_date,
        close=0.0,
        volume=0.0,
        data_quality=DQ_MISSING,
        eligible=False,
        exit_triggered=False,
        in_position_before=in_position,
        in_position_after=in_position,
        signal=None,
        indicators={},
    )


def evaluate_latest(
    df: pd.DataFrame,
    config: HybridStrategyConfig,
    in_position: bool,
    session_date: date,
) -> HybridEvaluation:
    """Evaluate exactly one completed session - the unit of work for the
    live daily scanner.

    `session_date` is the trading session the caller has already decided
    is complete (it never inspects wall-clock time itself - see
    `app/services/signal_service.py`). Three outcomes, all returned as a
    tagged `data_quality`, never silently skipped:

    - An exact bar for `session_date` exists: evaluated normally (still
      may come back `insufficient` if warmup hasn't completed).
    - No exact bar, but a usable bar exists within `max_staleness_days`:
      `stale` - the provider hasn't caught up yet, no signal generated.
    - Nothing usable at all (empty df, or the latest bar is older than
      the staleness tolerance): `missing`.
    """
    if df.empty:
        return _missing_evaluation(session_date, in_position)

    indicators = compute_indicators(df, config)
    exact = indicators.index[indicators["date"] == session_date]

    if len(exact) > 0:
        idx = int(exact[0])
        row = indicators.loc[idx]
        dq = _row_data_quality(row, config, idx, session_date)
    else:
        prior = indicators[indicators["date"] <= session_date]
        if prior.empty:
            return _missing_evaluation(session_date, in_position)
        idx = int(prior.index[-1])
        row = indicators.loc[idx]
        staleness_days = (session_date - row["date"]).days
        if staleness_days > config.max_staleness_days:
            return _missing_evaluation(session_date, in_position)
        dq = DQ_STALE

    eligible = dq == DQ_OK and _is_eligible(row, config)
    exit_triggered = dq == DQ_OK and in_position and _is_exit(row)

    signal: str | None = None
    in_position_after = in_position
    if not in_position and eligible:
        signal = BUY
        in_position_after = True
    elif in_position and exit_triggered:
        signal = SELL
        in_position_after = False

    return HybridEvaluation(
        date=session_date,
        close=float(row["close"]),
        volume=float(row["volume"]) if pd.notna(row["volume"]) else 0.0,
        data_quality=dq,
        eligible=eligible,
        exit_triggered=exit_triggered,
        in_position_before=in_position,
        in_position_after=in_position_after,
        signal=signal,
        indicators=_indicator_snapshot(row),
    )


@dataclass
class HybridEquityPoint:
    date: date
    close: float
    equity: float
    in_position: bool
    data_quality: str
    sma_mid: float | None = None
    sma_long: float | None = None


@dataclass
class HybridBacktestResult:
    """Backtest of the hybrid strategy, executed one session after the
    close-confirmed signal (next-open execution model - see module
    docstring in `app/services/backtest_service.py` for why this, not
    same-bar fill, is the default to avoid look-ahead bias).

    `cost_bps` (round-trip-each-way, e.g. 10 = 0.10%) is applied to both
    entry and exit fills, so `total_return_pct` is net of a simple flat
    cost model - not a full brokerage/STT/stamp-duty breakdown, which
    varies by broker and is out of scope here. This is disclosed, not
    hidden, in the API response (`cost_model` field).
    """

    equity_curve: list[HybridEquityPoint]
    trades: list[Trade]
    initial_capital: float
    cost_bps: float
    lookback_bars: int
    warmup_complete_date: date | None = None

    @property
    def is_fully_warmed_up(self) -> bool:
        if self.warmup_complete_date is None or not self.equity_curve:
            return False
        return self.warmup_complete_date == self.equity_curve[0].date

    @property
    def final_equity(self) -> float:
        return self.equity_curve[-1].equity if self.equity_curve else self.initial_capital

    @property
    def total_return_pct(self) -> float:
        if self.initial_capital <= 0:
            return 0.0
        return (self.final_equity / self.initial_capital - 1) * 100

    @property
    def buy_and_hold_return_pct(self) -> float:
        if len(self.equity_curve) < 2 or self.equity_curve[0].close <= 0:
            return 0.0
        return (self.equity_curve[-1].close / self.equity_curve[0].close - 1) * 100

    @property
    def max_drawdown_pct(self) -> float:
        peak = float("-inf")
        max_dd = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak > 0:
                max_dd = min(max_dd, (point.equity - peak) / peak * 100)
        return max_dd

    @property
    def closed_trades(self) -> list[Trade]:
        return [t for t in self.trades if not t.is_open]

    @property
    def win_rate_pct(self) -> float:
        closed = self.closed_trades
        if not closed:
            return 0.0
        wins = sum(1 for t in closed if t.return_pct > 0)
        return wins / len(closed) * 100

    @property
    def avg_trade_return_pct(self) -> float:
        closed = self.closed_trades
        if not closed:
            return 0.0
        return sum(t.return_pct for t in closed) / len(closed)

    @property
    def cagr_pct(self) -> float:
        if len(self.equity_curve) < 2 or self.initial_capital <= 0:
            return 0.0
        days = (self.equity_curve[-1].date - self.equity_curve[0].date).days
        if days <= 0:
            return 0.0
        ratio = self.final_equity / self.initial_capital
        if ratio <= 0:
            return -100.0
        years = days / 365.25
        return (ratio ** (1 / years) - 1) * 100

    @property
    def volatility_pct_annualized(self) -> float:
        """Annualized stdev of daily equity returns - 0 if fewer than 2 points."""
        if len(self.equity_curve) < 3:
            return 0.0
        equities = np.array([p.equity for p in self.equity_curve], dtype=float)
        daily_returns = equities[1:] / equities[:-1] - 1
        if daily_returns.size == 0:
            return 0.0
        return float(np.std(daily_returns, ddof=1) * np.sqrt(252) * 100)

    @property
    def sharpe_ratio(self) -> float | None:
        """Annualized Sharpe using a 0% risk-free rate (not risk-adjusted
        against an actual T-bill rate - disclosed, not a precise figure).
        None when volatility is 0 (e.g. no trades at all) - a Sharpe ratio
        is not meaningfully defined in that case."""
        vol = self.volatility_pct_annualized
        if vol <= 0:
            return None
        return self.cagr_pct / vol

    @property
    def exposure_pct(self) -> float:
        """Share of evaluated sessions spent in a position."""
        if not self.equity_curve:
            return 0.0
        in_pos = sum(1 for p in self.equity_curve if p.in_position)
        return in_pos / len(self.equity_curve) * 100

    @property
    def turnover(self) -> int:
        """Number of completed round-trips (closed trades)."""
        return len(self.closed_trades)


def run_hybrid_backtest(
    prices: pd.DataFrame,
    config: HybridStrategyConfig,
    start_date: date,
    end_date: date,
    initial_capital: float = 100_000.0,
    cost_bps: float = 0.0,
) -> HybridBacktestResult:
    """Long-only hybrid-strategy backtest, one position at a time.

    Execution model: a BUY/SELL signal is confirmed using a completed
    session's close (no look-ahead - `evaluate_series` only ever sees
    bars up to and including the row being evaluated). The simulated fill
    happens at the *next* available session's close in `prices` after the
    signal bar (an approximation of "next session's open" - this
    PriceHistory table does not store a separate next-session open
    price point distinct from that session's own OHLC open, so the
    close-execution convention from the existing SMA backtester is kept
    for consistency rather than introducing a second, differently-timed
    convention). This is deliberately conservative: the signal bar itself
    is never used as the fill price.
    """
    df = prices.sort_values("date").reset_index(drop=True)
    lookback_bars = int((df["date"] < start_date).sum())

    evaluations = evaluate_series(df, config, in_position_start=False, end_date=end_date)
    by_date = {e.date: e for e in evaluations}
    all_dates = sorted(by_date)

    window_dates = [d for d in all_dates if start_date <= d <= end_date]

    # Mirrors run_sma_crossover_backtest's semantics: "warmed up" is judged
    # from the first day *of the requested window*, not from the absolute
    # start of whatever extra lookback history was fetched for warmup.
    warmup_complete_date: date | None = None
    for d in window_dates:
        if by_date[d].data_quality != DQ_INSUFFICIENT:
            warmup_complete_date = d
            break

    equity_curve: list[HybridEquityPoint] = []
    trades: list[Trade] = []

    cash = initial_capital
    shares = 0.0
    entry_date: date | None = None
    entry_price: float | None = None
    pending_fill: str | None = None  # "BUY" or "SELL" to execute on the *next* bar

    cost_factor = cost_bps / 10_000.0

    for d in window_dates:
        ev = by_date[d]

        if pending_fill == "BUY" and shares == 0:
            fill_price = ev.close * (1 + cost_factor)
            shares = cash / fill_price
            cash = 0.0
            entry_date = d
            entry_price = fill_price
            pending_fill = None
        elif pending_fill == "SELL" and shares > 0:
            fill_price = ev.close * (1 - cost_factor)
            cash = shares * fill_price
            trades.append(Trade(entry_date, entry_price, d, fill_price, is_open=False))
            shares = 0.0
            entry_date = None
            entry_price = None
            pending_fill = None

        if ev.signal == BUY and shares == 0 and pending_fill is None:
            pending_fill = "BUY"
        elif ev.signal == SELL and shares > 0 and pending_fill is None:
            pending_fill = "SELL"

        equity_curve.append(
            HybridEquityPoint(
                date=d,
                close=ev.close,
                equity=cash + shares * ev.close,
                in_position=shares > 0,
                data_quality=ev.data_quality,
                sma_mid=ev.indicators.get("sma_mid"),
                sma_long=ev.indicators.get("sma_long"),
            )
        )

    if shares > 0 and entry_date is not None and entry_price is not None and equity_curve:
        last = equity_curve[-1]
        trades.append(Trade(entry_date, entry_price, last.date, last.close, is_open=True))

    return HybridBacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        initial_capital=initial_capital,
        cost_bps=cost_bps,
        lookback_bars=lookback_bars,
        warmup_complete_date=warmup_complete_date,
    )
