"""Yahoo Finance implementation of MarketDataProvider.

This is the only module in the codebase that imports/uses yfinance
directly. It fetches raw data from Yahoo Finance and normalizes it into
the plain dict representation defined by MarketDataProvider — callers
never see yfinance/pandas types.
"""

from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError, YFTickerMissingError

from app.data.ingestion.provider import (
    MarketDataProvider,
    MarketDataProviderError,
    NoDataFoundError,
    SymbolNotFoundError,
)

_OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


class YahooFinanceProvider(MarketDataProvider):
    """Market data provider backed by the yfinance library."""

    def get_price_history(
        self, symbol: str, start: date, end: date, interval: str = "1d"
    ) -> list[dict[str, Any]]:
        if start > end:
            raise ValueError("start date must not be after end date")

        try:
            history = yf.Ticker(symbol).history(
                start=start,
                end=end + timedelta(days=1),
                interval=interval,
                auto_adjust=False,
            )
        except YFTickerMissingError as exc:
            raise SymbolNotFoundError(f"Symbol '{symbol}' was not found.") from exc
        except YFRateLimitError as exc:
            raise MarketDataProviderError("Yahoo Finance rate limit exceeded.") from exc
        except Exception as exc:  # noqa: BLE001 - network/parsing failures from yfinance
            raise MarketDataProviderError(
                f"Failed to fetch data for '{symbol}' from Yahoo Finance: {exc}"
            ) from exc

        if history.empty:
            raise NoDataFoundError(
                f"No price data found for '{symbol}' between {start} and {end}."
            )

        return self._normalize(history)

    def get_latest_price(self, symbol: str) -> dict[str, Any]:
        raise NotImplementedError("get_latest_price is not implemented yet.")

    @staticmethod
    def _normalize(history: pd.DataFrame) -> list[dict[str, Any]]:
        """Convert a yfinance OHLCV DataFrame into our internal record list."""
        has_adjusted_close = "Adj Close" in history.columns
        records: list[dict[str, Any]] = []

        for index, row in history.iterrows():
            if row[list(_OHLCV_COLUMNS)].isna().any():
                continue

            trade_date = index.date() if hasattr(index, "date") else index
            adjusted_close = row["Adj Close"] if has_adjusted_close else row["Close"]

            records.append(
                {
                    "date": trade_date,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "adjusted_close": float(adjusted_close),
                    "volume": int(row["Volume"]),
                }
            )

        return records
