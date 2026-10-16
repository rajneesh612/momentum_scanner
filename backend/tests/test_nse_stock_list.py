"""Tests for the NIFTY 500 fetcher. Never makes real network calls."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.data.ingestion.nse_stock_list import StockListFetchError, fetch_nifty500

_SAMPLE_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Tata Consultancy Services Ltd.,IT,TCS,EQ,INE467B01029\n"
    "Reliance Industries Ltd.,Oil & Gas,RELIANCE,EQ,INE002A01018\n"
)


def test_fetch_nifty500_parses_remote_csv() -> None:
    mock_response = MagicMock()
    mock_response.text = _SAMPLE_CSV
    mock_response.raise_for_status.return_value = None

    with patch("app.data.ingestion.nse_stock_list.httpx.get", return_value=mock_response):
        records = fetch_nifty500()

    assert records == [
        {
            "symbol": "TCS.NS",
            "name": "Tata Consultancy Services Ltd.",
            "sector": "IT",
            "exchange": "NSE",
        },
        {
            "symbol": "RELIANCE.NS",
            "name": "Reliance Industries Ltd.",
            "sector": "Oil & Gas",
            "exchange": "NSE",
        },
    ]


def test_fetch_nifty500_reads_local_file(tmp_path) -> None:
    csv_path = tmp_path / "nifty500.csv"
    csv_path.write_text(_SAMPLE_CSV, encoding="utf-8")

    records = fetch_nifty500(source=csv_path)

    assert len(records) == 2
    assert records[0]["symbol"] == "TCS.NS"


def test_fetch_nifty500_raises_on_http_error() -> None:
    with (
        patch(
            "app.data.ingestion.nse_stock_list.httpx.get", side_effect=httpx.ConnectError("boom")
        ),
        pytest.raises(StockListFetchError),
    ):
        fetch_nifty500()


def test_fetch_nifty500_raises_on_empty_result() -> None:
    mock_response = MagicMock()
    mock_response.text = "Company Name,Industry,Symbol,Series,ISIN Code\n"
    mock_response.raise_for_status.return_value = None

    with (
        patch("app.data.ingestion.nse_stock_list.httpx.get", return_value=mock_response),
        pytest.raises(StockListFetchError),
    ):
        fetch_nifty500()
