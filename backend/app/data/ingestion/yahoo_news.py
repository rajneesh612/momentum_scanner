"""Yahoo Finance implementation of NewsProvider.

Backed by yfinance's unofficial `Ticker.get_news()` endpoint. This is the
only module that imports/uses yfinance for news.

Known limitations (disclose these, never paper over them):
- This is an unofficial, undocumented endpoint — not a dedicated
  corporate-actions/events feed. It returns general news headlines about
  the ticker, not structured "buyback announced" records.
- It typically only exposes recent items, not deep historical coverage.
  Do not assume this can backfill years of past events.
- Its response shape has changed across yfinance/Yahoo versions and isn't
  guaranteed stable; articles that don't parse cleanly are skipped, never
  guessed at.
- Verified live during development (2026-10-16): this endpoint currently
  returns zero results for every symbol tested, including US mega-caps
  like AAPL — so today, in this environment, no real events flow through
  it. The parsing logic below is written defensively against the known
  historical response shapes and is unit-tested against representative
  fixtures, but has not been verified against a live, non-empty response.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yfinance as yf

from app.data.ingestion.news_provider import NewsProvider, NewsProviderError, RawEvent

# Ordered (most-specific-first) keyword -> category rules. Pure best-effort
# text classification over the headline — not structured data from any
# source. First match wins; "other" is the honest default otherwise.
_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("buyback", "buyback"),
    ("dividend", "dividend"),
    ("merger", "ma"),
    ("acquisition", "ma"),
    ("acquire", "ma"),
    ("amalgamat", "ma"),
    ("stake sale", "ma"),
    ("bags order", "order_win"),
    ("wins order", "order_win"),
    ("secures order", "order_win"),
    ("order win", "order_win"),
    ("contract win", "order_win"),
    ("sebi", "regulatory"),
    (" rbi ", "regulatory"),
    ("regulatory", "regulatory"),
    ("penalty", "regulatory"),
    ("show cause", "regulatory"),
    ("qip", "fundraising"),
    ("rights issue", "fundraising"),
    ("fund raising", "fundraising"),
    ("fundraise", "fundraising"),
    ("preferential allotment", "fundraising"),
    ("fpo", "fundraising"),
    ("q1 result", "earnings"),
    ("q2 result", "earnings"),
    ("q3 result", "earnings"),
    ("q4 result", "earnings"),
    ("quarterly result", "earnings"),
    ("net profit", "earnings"),
    ("earnings", "earnings"),
    ("results:", "earnings"),
)


def classify_event_category(title: str) -> str:
    """Best-effort category from headline text alone. Never authoritative."""
    lowered = f" {title.lower()} "
    for keyword, category in _CATEGORY_RULES:
        if keyword in lowered:
            return category
    return "other"


def _nested_url(block: Any) -> str | None:
    if isinstance(block, dict):
        url = block.get("url")
        return url if isinstance(url, str) else None
    if isinstance(block, str):
        return block
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def _parse_article(article: dict[str, Any]) -> RawEvent | None:
    """Parse one raw article dict into a RawEvent, or None if it's missing
    a field we're unwilling to guess at (title, URL, or a publish time).
    """
    content = article.get("content") if isinstance(article.get("content"), dict) else article

    title = content.get("title")
    if not title or not isinstance(title, str):
        return None

    url = (
        _nested_url(content.get("canonicalUrl"))
        or _nested_url(content.get("clickThroughUrl"))
        or content.get("link")
    )
    if not url:
        return None

    published_raw = (
        content.get("pubDate") or content.get("providerPublishTime") or content.get("displayTime")
    )
    published_at = _parse_timestamp(published_raw)
    if published_at is None:
        return None

    provider_block = content.get("provider")
    if isinstance(provider_block, dict):
        source_name = provider_block.get("displayName") or "Yahoo Finance"
    else:
        source_name = content.get("publisher") or "Yahoo Finance"

    provider_event_id = article.get("id") or content.get("uuid") or url
    summary = content.get("summary") or content.get("description")
    summary = summary if isinstance(summary, str) else None

    return RawEvent(
        provider="yahoo_finance",
        provider_event_id=str(provider_event_id),
        title=title,
        category=classify_event_category(title),
        summary=summary,
        published_at=published_at,
        source_name=str(source_name),
        source_url=str(url),
    )


class YahooNewsProvider(NewsProvider):
    """News provider backed by yfinance's unofficial news endpoint."""

    def get_events(self, symbol: str, count: int = 20) -> list[RawEvent]:
        try:
            articles = yf.Ticker(symbol).get_news(count=count)
        except Exception as exc:  # noqa: BLE001 - network/parsing failures from yfinance
            raise NewsProviderError(
                f"Failed to fetch news for '{symbol}' from Yahoo Finance: {exc}"
            ) from exc

        events: list[RawEvent] = []
        for article in articles or []:
            event = _parse_article(article)
            if event is not None:
                events.append(event)
        return events
