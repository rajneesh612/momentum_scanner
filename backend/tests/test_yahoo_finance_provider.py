"""Unit tests for YahooFinanceProvider.

These tests mock yfinance.Ticker directly, so they never make real network
calls to Yahoo Finance.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from yfinance.exceptions import YFTickerMissingError

from app.data.ingestion.provider import NoDataFoundError, SymbolNotFoundError
from app.data.ingestion.yahoo_finance import YahooFinanceProvider


def _history_df() -> pd.DataFrame:
    index = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 100.0],
            "Close": [104.0, 105.0],
            "Adj Close": [103.5, 104.5],
            "Volume": [1_000_000, 1_100_000],
        },
        index=index,
    )


def test_get_price_history_normalizes_data() -> None:
    provider = YahooFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _history_df()

    with patch("app.data.ingestion.yahoo_finance.yf.Ticker", return_value=mock_ticker):
        records = provider.get_price_history("RELIANCE.NS", date(2024, 1, 1), date(2024, 1, 5))

    assert records == [
        {
            "date": date(2024, 1, 2),
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "adjusted_close": 103.5,
            "volume": 1_000_000,
        },
        {
            "date": date(2024, 1, 3),
            "open": 101.0,
            "high": 106.0,
            "low": 100.0,
            "close": 105.0,
            "adjusted_close": 104.5,
            "volume": 1_100_000,
        },
    ]


def test_get_price_history_falls_back_to_close_when_adj_close_missing() -> None:
    provider = YahooFinanceProvider()
    df = _history_df().drop(columns=["Adj Close"])
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df

    with patch("app.data.ingestion.yahoo_finance.yf.Ticker", return_value=mock_ticker):
        records = provider.get_price_history("RELIANCE.NS", date(2024, 1, 1), date(2024, 1, 5))

    assert records[0]["adjusted_close"] == records[0]["close"] == 104.0


def test_get_price_history_raises_no_data_found_on_empty_result() -> None:
    provider = YahooFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()

    with (
        patch("app.data.ingestion.yahoo_finance.yf.Ticker", return_value=mock_ticker),
        pytest.raises(NoDataFoundError),
    ):
        provider.get_price_history("RELIANCE.NS", date(2024, 1, 1), date(2024, 1, 5))


def test_get_price_history_raises_symbol_not_found_for_missing_ticker() -> None:
    provider = YahooFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = YFTickerMissingError("BADSYMBOL", "possibly delisted")

    with (
        patch("app.data.ingestion.yahoo_finance.yf.Ticker", return_value=mock_ticker),
        pytest.raises(SymbolNotFoundError),
    ):
        provider.get_price_history("BADSYMBOL", date(2024, 1, 1), date(2024, 1, 5))


def test_get_price_history_rejects_invalid_date_range() -> None:
    provider = YahooFinanceProvider()

    with pytest.raises(ValueError):
        provider.get_price_history("RELIANCE.NS", date(2024, 1, 5), date(2024, 1, 1))


def test_get_price_history_passes_interval_through_to_yfinance() -> None:
    provider = YahooFinanceProvider()
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _history_df()

    with patch("app.data.ingestion.yahoo_finance.yf.Ticker", return_value=mock_ticker):
        provider.get_price_history(
            "RELIANCE.NS", date(2024, 1, 1), date(2024, 1, 5), interval="1wk"
        )

    assert mock_ticker.history.call_args.kwargs["interval"] == "1wk"
