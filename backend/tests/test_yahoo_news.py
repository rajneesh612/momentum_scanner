"""Tests for the Yahoo news provider's category classifier and article
parser. These never make real network calls - they operate on crafted
fixture dicts representing the historically-known response shapes, since
the live endpoint returned zero results for every symbol tested during
development (see yahoo_news.py's module docstring).
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.data.ingestion.news_provider import NewsProviderError
from app.data.ingestion.yahoo_news import YahooNewsProvider, classify_event_category


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Company announces share buyback worth Rs 1,000 crore", "buyback"),
        ("Board declares interim dividend of Rs 5 per share", "dividend"),
        ("Firm to acquire majority stake in rival", "ma"),
        ("Company bags order worth Rs 500 crore from Indian Railways", "order_win"),
        ("SEBI imposes penalty on company for disclosure lapses", "regulatory"),
        ("Company plans QIP to raise Rs 2,000 crore", "fundraising"),
        ("Q2 results: net profit rises 12% YoY", "earnings"),
        ("Company launches new product line", "other"),
    ],
)
def test_classify_event_category(title: str, expected: str) -> None:
    assert classify_event_category(title) == expected


def _nested_article(**overrides: object) -> dict:
    content = {
        "title": "Company announces share buyback",
        "summary": "The board approved a buyback of up to 2% of equity.",
        "pubDate": "2026-01-15T10:30:00Z",
        "provider": {"displayName": "Moneycontrol"},
        "canonicalUrl": {"url": "https://example.com/article-1"},
    }
    content.update(overrides)
    return {"id": "abc123", "content": content}


def test_parses_nested_content_shape() -> None:
    provider = YahooNewsProvider()
    with patch(
        "app.data.ingestion.yahoo_news.yf.Ticker",
        return_value=MagicMock(get_news=MagicMock(return_value=[_nested_article()])),
    ):
        events = provider.get_events("RELIANCE.NS")

    assert len(events) == 1
    event = events[0]
    assert event.provider == "yahoo_finance"
    assert event.provider_event_id == "abc123"
    assert event.title == "Company announces share buyback"
    assert event.category == "buyback"
    assert event.source_name == "Moneycontrol"
    assert event.source_url == "https://example.com/article-1"
    assert event.published_at == datetime(2026, 1, 15, 10, 30, tzinfo=UTC)


def test_parses_flat_legacy_shape() -> None:
    flat_article = {
        "uuid": "legacy-uuid-1",
        "title": "Quarterly results announced",
        "link": "https://example.com/legacy",
        "publisher": "Reuters",
        "providerPublishTime": 1700000000,
    }
    provider = YahooNewsProvider()
    with patch(
        "app.data.ingestion.yahoo_news.yf.Ticker",
        return_value=MagicMock(get_news=MagicMock(return_value=[flat_article])),
    ):
        events = provider.get_events("RELIANCE.NS")

    assert len(events) == 1
    assert events[0].provider_event_id == "legacy-uuid-1"
    assert events[0].source_name == "Reuters"
    assert events[0].published_at == datetime.fromtimestamp(1700000000, tz=UTC)


def test_skips_articles_missing_required_fields() -> None:
    # No title, no URL, no publish time - never guessed at, just dropped.
    bad_articles = [
        {"content": {"summary": "no title here"}},
        {"content": {"title": "Has a title but no URL or date"}},
        _nested_article(),  # one good one, to prove the others are skipped not fatal
    ]
    provider = YahooNewsProvider()
    with patch(
        "app.data.ingestion.yahoo_news.yf.Ticker",
        return_value=MagicMock(get_news=MagicMock(return_value=bad_articles)),
    ):
        events = provider.get_events("RELIANCE.NS")

    assert len(events) == 1


def test_wraps_fetch_failures_as_news_provider_error() -> None:
    provider = YahooNewsProvider()
    with (
        patch(
            "app.data.ingestion.yahoo_news.yf.Ticker",
            return_value=MagicMock(get_news=MagicMock(side_effect=RuntimeError("boom"))),
        ),
        pytest.raises(NewsProviderError),
    ):
        provider.get_events("RELIANCE.NS")
