"""Tests for the pure SMA crossover backtest engine (no FastAPI/DB)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from app.momentum.backtest import BacktestResult, EquityPoint, Trade, run_sma_crossover_backtest


def _dates(n: int, start: date = date(2024, 1, 1)) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def test_sma_crossover_opens_and_closes_trades_on_signal_flips() -> None:
    # short_window=1 (SMA(1) == close), long_window=2, so the math is easy
    # to hand-verify. Day-by-day: flat, flat, buy@12, hold, sell@11, flat,
    # buy@13, still holding at the end (open trade, marked at 15).
    dates = _dates(8)
    closes = [10, 10, 12, 14, 11, 9, 13, 15]
    df = pd.DataFrame({"date": dates, "close": closes})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=1000.0,
    )

    assert len(result.trades) == 2
    closed, open_trade = result.trades

    assert closed.entry_date == dates[2]
    assert closed.entry_price == 12
    assert closed.exit_date == dates[4]
    assert closed.exit_price == 11
    assert closed.is_open is False
    assert closed.return_pct == pytest.approx((11 / 12 - 1) * 100)

    assert open_trade.entry_date == dates[6]
    assert open_trade.entry_price == 13
    assert open_trade.exit_date == dates[7]
    assert open_trade.exit_price == 15
    assert open_trade.is_open is True

    assert len(result.equity_curve) == 8
    assert result.equity_curve[0].equity == pytest.approx(1000.0)
    assert result.equity_curve[2].in_position is True
    assert result.equity_curve[4].in_position is False
    assert result.equity_curve[-1].equity == pytest.approx(1000.0 * (11 / 12) * (15 / 13))

    assert result.final_equity == pytest.approx(result.equity_curve[-1].equity)
    assert result.buy_and_hold_return_pct == pytest.approx((15 / 10 - 1) * 100)


def test_equity_curve_exposes_short_and_long_sma_values() -> None:
    # short_window=1 (SMA(1) == close), long_window=2.
    dates = _dates(4)
    closes = [10, 10, 12, 14]
    df = pd.DataFrame({"date": dates, "close": closes})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=1000.0,
    )

    # Day 0: no prior bar, long SMA(2) not yet valid.
    assert result.equity_curve[0].short_sma == pytest.approx(10)
    assert result.equity_curve[0].long_sma is None
    # Day 1 onward: both SMAs valid and match a hand-computed rolling mean.
    assert result.equity_curve[1].short_sma == pytest.approx(10)
    assert result.equity_curve[1].long_sma == pytest.approx((10 + 10) / 2)
    assert result.equity_curve[2].short_sma == pytest.approx(12)
    assert result.equity_curve[2].long_sma == pytest.approx((10 + 12) / 2)
    assert result.equity_curve[3].short_sma == pytest.approx(14)
    assert result.equity_curve[3].long_sma == pytest.approx((12 + 14) / 2)


def test_trade_dates_align_with_exposed_sma_crossover_points() -> None:
    # The frontend places BUY/SELL markers using `trades` dates and draws
    # SMA lines using `equity_curve[*].short_sma/long_sma` — this proves
    # those two things actually agree: a trade's entry/exit date is
    # exactly a bar where the exposed SMAs crossed.
    dates = _dates(8)
    closes = [10, 10, 12, 14, 11, 9, 13, 15]
    df = pd.DataFrame({"date": dates, "close": closes})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=1000.0,
    )
    by_date = {p.date: p for p in result.equity_curve}

    for trade in result.closed_trades:
        entry_point = by_date[trade.entry_date]
        assert entry_point.short_sma is not None
        assert entry_point.long_sma is not None
        assert entry_point.short_sma > entry_point.long_sma

        exit_point = by_date[trade.exit_date]
        assert exit_point.short_sma is not None
        assert exit_point.long_sma is not None
        assert exit_point.short_sma <= exit_point.long_sma


def test_no_crossover_stays_flat_and_matches_initial_capital() -> None:
    dates = _dates(5)
    df = pd.DataFrame({"date": dates, "close": [10.0] * 5})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=500.0,
    )

    assert result.trades == []
    assert all(point.equity == pytest.approx(500.0) for point in result.equity_curve)
    assert all(point.in_position is False for point in result.equity_curve)
    assert result.final_equity == pytest.approx(500.0)


def test_lookback_bars_counts_rows_before_start_date() -> None:
    dates = _dates(10)
    df = pd.DataFrame({"date": dates, "close": [10.0] * 10})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[6],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=100.0,
    )

    assert result.lookback_bars == 6
    assert len(result.equity_curve) == 4


def test_insufficient_warmup_data_never_signals() -> None:
    # long_window=200 but only 5 rows of history exist anywhere - SMA(200)
    # is NaN for the whole window, so the strategy should never go long.
    dates = _dates(5)
    df = pd.DataFrame({"date": dates, "close": [10, 11, 12, 13, 14]})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=200,
        initial_capital=1000.0,
    )

    assert result.trades == []
    assert all(point.equity == pytest.approx(1000.0) for point in result.equity_curve)


def test_max_drawdown_pct_tracks_peak_to_trough() -> None:
    points = [
        EquityPoint(date(2024, 1, 1), 10, 1000, False),
        EquityPoint(date(2024, 1, 2), 12, 1200, True),
        EquityPoint(date(2024, 1, 3), 9, 900, True),
        EquityPoint(date(2024, 1, 4), 11, 1100, True),
    ]
    result = BacktestResult(equity_curve=points, trades=[], initial_capital=1000.0, lookback_bars=0)

    assert result.max_drawdown_pct == pytest.approx((900 - 1200) / 1200 * 100)


def test_win_rate_pct_counts_only_closed_trades() -> None:
    trades = [
        Trade(date(2024, 1, 1), 10, date(2024, 1, 2), 12, is_open=False),  # win
        Trade(date(2024, 1, 3), 10, date(2024, 1, 4), 9, is_open=False),  # loss
        Trade(date(2024, 1, 5), 10, date(2024, 1, 6), 20, is_open=True),  # open, excluded
    ]
    result = BacktestResult(equity_curve=[], trades=trades, initial_capital=1000.0, lookback_bars=0)

    assert result.win_rate_pct == pytest.approx(50.0)
    assert len(result.closed_trades) == 2


def test_warmup_complete_date_is_none_when_never_warmed_up() -> None:
    dates = _dates(5)
    df = pd.DataFrame({"date": dates, "close": [10, 11, 12, 13, 14]})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=200,
        initial_capital=1000.0,
    )

    assert result.warmup_complete_date is None
    assert result.is_fully_warmed_up is False


def test_warmup_complete_date_reflects_first_valid_long_sma_row() -> None:
    # long_window=2 needs 2 points; the window's own first day only has 1
    # (no lookback), so the SMA isn't valid until the window's 2nd day.
    dates = _dates(4)
    df = pd.DataFrame({"date": dates, "close": [10, 11, 12, 13]})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[0],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=1000.0,
    )

    assert result.warmup_complete_date == dates[1]
    assert result.is_fully_warmed_up is False


def test_is_fully_warmed_up_true_when_lookback_covers_long_window() -> None:
    # 2 lookback bars before start_date give long_window=2 a valid value
    # right from the first simulated day.
    dates = _dates(5)
    df = pd.DataFrame({"date": dates, "close": [10, 11, 12, 13, 14]})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[2],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=1000.0,
    )

    assert result.warmup_complete_date == dates[2]
    assert result.is_fully_warmed_up is True
    assert result.lookback_bars == 2


def test_equity_curve_starts_at_initial_capital_even_with_day_one_trade() -> None:
    # Lookback day (5) is low enough that the window's very first bar (10)
    # already triggers a same-day buy signal.
    dates = _dates(3)
    df = pd.DataFrame({"date": dates, "close": [5, 10, 9]})

    result = run_sma_crossover_backtest(
        df,
        start_date=dates[1],
        end_date=dates[-1],
        short_window=1,
        long_window=2,
        initial_capital=50_000.0,
    )

    assert result.equity_curve[0].in_position is True
    assert result.equity_curve[0].equity == pytest.approx(50_000.0)


def test_no_lookahead_bias_earlier_bars_unaffected_by_later_prices() -> None:
    # Only the last day's close differs between the two runs. If a future
    # bar ever leaked into an earlier bar's signal or equity, bar values
    # before that last day would differ too - they must not.
    dates = _dates(6)
    df_a = pd.DataFrame({"date": dates, "close": [10, 11, 12, 13, 14, 15]})
    df_b = pd.DataFrame({"date": dates, "close": [10, 11, 12, 13, 14, 999]})

    kwargs = {
        "start_date": dates[0],
        "end_date": dates[-1],
        "short_window": 2,
        "long_window": 3,
        "initial_capital": 1000.0,
    }
    result_a = run_sma_crossover_backtest(df_a, **kwargs)
    result_b = run_sma_crossover_backtest(df_b, **kwargs)

    paired = zip(result_a.equity_curve[:-1], result_b.equity_curve[:-1], strict=True)
    for point_a, point_b in paired:
        assert point_a.equity == pytest.approx(point_b.equity)
        assert point_a.in_position == point_b.in_position


def test_cagr_pct_for_a_full_year_double() -> None:
    points = [
        EquityPoint(date(2024, 1, 1), 10, 1000.0, False),
        EquityPoint(date(2024, 12, 31), 20, 2000.0, False),
    ]
    result = BacktestResult(equity_curve=points, trades=[], initial_capital=1000.0, lookback_bars=0)

    assert result.cagr_pct == pytest.approx(100.0, abs=1.0)
