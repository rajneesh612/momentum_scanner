"""Tests for the NSE corporate-announcements provider. Never makes real
network calls — fixtures mirror the real response shape observed live
during development (see nse_announcements.py's module docstring).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.data.ingestion.news_provider import NewsProviderError
from app.data.ingestion.nse_announcements import (
    NseAnnouncementsProvider,
    classify_announcement_category,
)


@pytest.mark.parametrize(
    ("desc", "expected"),
    [
        ("Acquisition", "ma"),
        ("Amalgamation / Merger", "ma"),
        ("Dividend", "dividend"),
        ("Buy Back", "buyback"),
        ("Allotment of Equity Shares", "fundraising"),
        ("Financial Results", "earnings"),
        ("Board Meeting Intimation", "earnings"),
        ("AGM", "other"),
        ("Copy of Newspaper Publication", "other"),
    ],
)
def test_classify_announcement_category(desc: str, expected: str) -> None:
    assert classify_announcement_category(desc) == expected


def _real_shape_item(**overrides: object) -> dict:
    item = {
        "an_dt": "15-Oct-2026 18:06:36",
        "attFileSize": "8.72 MB",
        "attchmntFile": "https://nsearchives.nseindia.com/corporate/test_file.pdf",
        "attchmntText": "Newspaper clippings of the advertisement published today.",
        "desc": "Copy of Newspaper Publication",
        "exchdisstime": "15-Oct-2026 18:06:37",
        "seq_id": "106819001",
        "sm_name": "Reliance Industries Limited",
        "symbol": "RELIANCE",
    }
    item.update(overrides)
    return item


def _mock_response(items: object, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = items
    error = httpx.HTTPStatusError("error", request=MagicMock(), response=response)
    response.raise_for_status.side_effect = None if status_code == 200 else error
    return response


def test_parses_real_observed_response_shape() -> None:
    provider = NseAnnouncementsProvider()
    mocked = _mock_response([_real_shape_item()])
    with patch("app.data.ingestion.nse_announcements.httpx.get", return_value=mocked):
        events = provider.get_events("RELIANCE.NS")

    assert len(events) == 1
    event = events[0]
    assert event.provider == "nse_corporate_announcements"
    assert event.provider_event_id == "106819001"
    assert event.title == "Copy of Newspaper Publication"
    assert event.category == "other"
    assert event.source_name == "NSE"
    assert event.source_url == "https://nsearchives.nseindia.com/corporate/test_file.pdf"
    assert event.summary == "Newspaper clippings of the advertisement published today."


def test_converts_ist_timestamp_to_utc() -> None:
    # 18:06:36 IST (UTC+5:30) -> 12:36:36 UTC.
    provider = NseAnnouncementsProvider()
    mocked = _mock_response([_real_shape_item()])
    with patch("app.data.ingestion.nse_announcements.httpx.get", return_value=mocked):
        events = provider.get_events("RELIANCE.NS")

    assert events[0].published_at == datetime(2026, 10, 15, 12, 36, 36, tzinfo=UTC)
    assert events[0].published_at.tzinfo is not None


def test_strips_exchange_suffix_when_querying() -> None:
    provider = NseAnnouncementsProvider()
    with patch(
        "app.data.ingestion.nse_announcements.httpx.get", return_value=_mock_response([])
    ) as mock_get:
        provider.get_events("RELIANCE.NS")

    assert mock_get.call_args.kwargs["params"]["symbol"] == "RELIANCE"


def test_respects_count_limit() -> None:
    items = [_real_shape_item(seq_id=str(i)) for i in range(10)]
    provider = NseAnnouncementsProvider()
    mocked = _mock_response(items)
    with patch("app.data.ingestion.nse_announcements.httpx.get", return_value=mocked):
        events = provider.get_events("RELIANCE.NS", count=3)

    assert len(events) == 3


def test_skips_items_missing_required_fields() -> None:
    items = [
        {"desc": "No URL or date"},
        {"attchmntFile": "https://example.com/x.pdf", "desc": "No date"},
        _real_shape_item(seq_id="good-1"),
    ]
    provider = NseAnnouncementsProvider()
    mocked = _mock_response(items)
    with patch("app.data.ingestion.nse_announcements.httpx.get", return_value=mocked):
        events = provider.get_events("RELIANCE.NS")

    assert len(events) == 1
    assert events[0].provider_event_id == "good-1"


def test_retries_once_then_succeeds() -> None:
    provider = NseAnnouncementsProvider()
    responses = [httpx.ConnectError("boom"), _mock_response([_real_shape_item()])]

    def side_effect(*args, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with (
        patch("app.data.ingestion.nse_announcements.httpx.get", side_effect=side_effect),
        patch("app.data.ingestion.nse_announcements.time.sleep"),
    ):
        events = provider.get_events("RELIANCE.NS")

    assert len(events) == 1


def test_raises_news_provider_error_after_exhausting_retries() -> None:
    provider = NseAnnouncementsProvider()
    with (
        patch(
            "app.data.ingestion.nse_announcements.httpx.get",
            side_effect=httpx.ConnectError("boom"),
        ),
        patch("app.data.ingestion.nse_announcements.time.sleep"),
        pytest.raises(NewsProviderError),
    ):
        provider.get_events("RELIANCE.NS")


def test_raises_on_non_list_response() -> None:
    provider = NseAnnouncementsProvider()
    with (
        patch(
            "app.data.ingestion.nse_announcements.httpx.get",
            return_value=_mock_response({"unexpected": "shape"}),
        ),
        pytest.raises(NewsProviderError),
    ):
        provider.get_events("RELIANCE.NS")
