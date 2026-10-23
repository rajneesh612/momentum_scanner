"""Tests for the pure hybrid trend/momentum/volume signal engine (no FastAPI/DB)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from app.momentum.hybrid_signal import (
    BUY,
    DQ_INSUFFICIENT,
    DQ_MISSING,
    DQ_OK,
    DQ_STALE,
    SELL,
    HybridStrategyConfig,
    evaluate_latest,
    evaluate_series,
    run_hybrid_backtest,
)

# Small windows so scenarios are hand-verifiable, mirroring how
# test_backtest_engine.py uses short_window=1/long_window=2 for the SMA engine.
_CONFIG = HybridStrategyConfig(
    sma_short=1,
    sma_mid=2,
    sma_long=3,
    momentum_short_days=1,
    momentum_long_days=2,
    volume_lookback=2,
    volume_multiplier=1.2,
    volatility_lookback=2,
    max_staleness_days=5,
)


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _scenario_df() -> tuple[list[date], pd.DataFrame]:
    """BUY at idx3, SELL at idx5, BUY at idx7, still open at idx9.

    Hand-verified in the implementation session - see comments inline for
    why each day lands where it does.
    """
    dates = _dates(10)
    closes = [10, 10, 10, 12, 14, 11, 10, 13, 15, 16]
    volumes = [100, 100, 100, 200, 100, 100, 100, 300, 100, 100]
    df = pd.DataFrame({"date": dates, "close": closes, "volume": volumes})
    return dates, df


def test_min_bars_required_accounts_for_momentum_and_sma_windows() -> None:
    assert _CONFIG.min_bars_required == max(3, 2 + 1)


def test_insufficient_data_quality_before_warmup() -> None:
    dates, df = _scenario_df()
    results = evaluate_series(df, _CONFIG)

    assert results[0].data_quality == DQ_INSUFFICIENT
    assert results[1].data_quality == DQ_INSUFFICIENT
    assert results[0].eligible is False
    # idx2 has enough bars (3) but momentum is exactly 0 (flat price) -
    # data is fine, the strategy's own threshold just isn't met.
    assert results[2].data_quality == DQ_OK
    assert results[2].eligible is False


def test_eligibility_requires_strict_sma_mid_above_sma_long() -> None:
    # idx6: close=10 after close=11 - sma_mid(10.5) < sma_long(11.667), and
    # momentum_short is negative anyway, so not eligible on either count.
    dates, df = _scenario_df()
    results = evaluate_series(df, _CONFIG)
    ev6 = results[6]
    assert ev6.indicators["sma_mid"] == pytest.approx(10.5)
    assert ev6.indicators["sma_long"] == pytest.approx(11.6666666, rel=1e-5)
    assert ev6.eligible is False
    assert ev6.signal is None


def test_full_buy_sell_buy_state_machine() -> None:
    dates, df = _scenario_df()
    results = evaluate_series(df, _CONFIG)
    signals = [(r.date, r.signal) for r in results if r.signal is not None]

    assert signals == [
        (dates[3], BUY),
        (dates[5], SELL),
        (dates[7], BUY),
    ]

    # No repeated BUY while already in position (idx4), no repeated SELL
    # while already flat (idx6).
    assert results[4].signal is None
    assert results[4].in_position_before is True
    assert results[6].signal is None
    assert results[6].in_position_before is False

    # Still holding at the end - mirrors the SMA engine's "open trade" idea.
    assert results[-1].in_position_after is True


def test_volume_condition_gates_an_otherwise_eligible_day() -> None:
    # Reuse idx3's trend/momentum setup but drop the volume spike - should
    # no longer be eligible.
    dates = _dates(4)
    df = pd.DataFrame(
        {
            "date": dates,
            "close": [10, 10, 10, 12],
            "volume": [100, 100, 100, 100],  # no spike this time
        }
    )
    results = evaluate_series(df, _CONFIG)
    assert results[3].eligible is False
    assert results[3].signal is None


def test_evaluate_latest_exact_session_match() -> None:
    dates, df = _scenario_df()
    ev = evaluate_latest(df, _CONFIG, in_position=False, session_date=dates[3])
    assert ev.data_quality == DQ_OK
    assert ev.signal == BUY
    assert ev.in_position_after is True


def test_evaluate_latest_missing_symbol_entirely() -> None:
    empty = pd.DataFrame({"date": [], "close": [], "volume": []})
    ev = evaluate_latest(empty, _CONFIG, in_position=False, session_date=date(2024, 1, 1))
    assert ev.data_quality == DQ_MISSING
    assert ev.signal is None


def test_evaluate_latest_stale_within_tolerance() -> None:
    dates, df = _scenario_df()
    # Ask for a session 2 days after the last available bar - within the
    # 5-day staleness tolerance, so "stale", not "missing" - and never a
    # fabricated signal.
    stale_session = dates[-1] + timedelta(days=2)
    ev = evaluate_latest(df, _CONFIG, in_position=False, session_date=stale_session)
    assert ev.data_quality == DQ_STALE
    assert ev.signal is None
    assert ev.eligible is False


def test_evaluate_latest_too_old_counts_as_missing() -> None:
    dates, df = _scenario_df()
    far_future = dates[-1] + timedelta(days=30)
    ev = evaluate_latest(df, _CONFIG, in_position=False, session_date=far_future)
    assert ev.data_quality == DQ_MISSING
    assert ev.signal is None


def test_evaluate_latest_never_fabricates_a_signal_on_bad_data() -> None:
    # Zero volume on an otherwise-eligible-looking day must not produce a
    # BUY - this is the "don't use incomplete/invalid data" guarantee.
    dates = _dates(4)
    df = pd.DataFrame(
        {"date": dates, "close": [10, 10, 10, 12], "volume": [100, 100, 100, 0]}
    )
    ev = evaluate_latest(df, _CONFIG, in_position=False, session_date=dates[3])
    assert ev.data_quality == DQ_INSUFFICIENT
    assert ev.signal is None


def test_hybrid_backtest_executes_on_next_bar_not_signal_bar() -> None:
    dates, df = _scenario_df()

    result = run_hybrid_backtest(
        df,
        _CONFIG,
        start_date=dates[0],
        end_date=dates[-1],
        initial_capital=1000.0,
        cost_bps=0.0,
    )

    assert len(result.trades) == 2
    closed, open_trade = result.trades

    # Signal confirmed at idx3 (close 12) - BUT filled at idx4's close
    # (14), never at the signal bar's own close. This is the no-look-ahead
    # guarantee under test.
    assert closed.entry_date == dates[4]
    assert closed.entry_price == pytest.approx(14)
    # Signal confirmed at idx5 - filled at idx6's close (10).
    assert closed.exit_date == dates[6]
    assert closed.exit_price == pytest.approx(10)

    assert open_trade.entry_date == dates[8]
    assert open_trade.entry_price == pytest.approx(15)
    assert open_trade.exit_date == dates[-1]
    assert open_trade.exit_price == pytest.approx(16)
    assert open_trade.is_open is True

    assert result.final_equity == pytest.approx(1000.0 * (10 / 14) * (16 / 15))
    assert result.turnover == 1  # one closed round-trip
    assert result.exposure_pct > 0


def test_hybrid_backtest_cost_bps_reduces_return_vs_zero_cost() -> None:
    dates, df = _scenario_df()

    free = run_hybrid_backtest(
        df, _CONFIG, start_date=dates[0], end_date=dates[-1], initial_capital=1000.0, cost_bps=0.0
    )
    costly = run_hybrid_backtest(
        df, _CONFIG, start_date=dates[0], end_date=dates[-1], initial_capital=1000.0, cost_bps=50.0
    )

    assert costly.final_equity < free.final_equity


def test_hybrid_backtest_warmup_complete_date_matches_window_start_when_padded() -> None:
    dates, df = _scenario_df()
    # Evaluate only from idx2 onward (dates[2] already has valid
    # indicators per test_insufficient_data_quality_before_warmup).
    result = run_hybrid_backtest(
        df, _CONFIG, start_date=dates[2], end_date=dates[-1], initial_capital=1000.0
    )
    assert result.warmup_complete_date == dates[2]
    assert result.is_fully_warmed_up is True


def test_hybrid_backtest_no_signal_in_window_means_no_trades_and_flat_equity() -> None:
    dates = _dates(4)
    df = pd.DataFrame(
        {"date": dates, "close": [10, 10, 10, 10], "volume": [100, 100, 100, 100]}
    )
    result = run_hybrid_backtest(
        df, _CONFIG, start_date=dates[0], end_date=dates[-1], initial_capital=1000.0
    )
    assert result.trades == []
    assert result.final_equity == pytest.approx(1000.0)
    assert result.sharpe_ratio is None
