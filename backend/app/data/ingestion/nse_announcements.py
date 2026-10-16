"""NSE corporate-announcements implementation of NewsProvider.

NSE itself publishes a structured, free, no-key JSON feed of corporate
announcements (board meetings, dividends, buybacks, M&A, AGMs, etc.) at
`nseindia.com/api/corporate-announcements`. Verified live during
development (2026-10-16): reachable without any cookie/session
bootstrap across repeated cold calls, `robots.txt` permits `/api/*`
(only `/market-data-test` is disallowed), and a single symbol can return
thousands of real, dated announcements with a genuine controlled-
vocabulary category field (`desc`) — a much better fit than generic
headline-based news for "corporate events" specifically.

Caveats, disclosed rather than glossed over:
- This is still an unofficial-for-third-party-use endpoint (it backs
  NSE's own website, not a published public API product) and its
  reliability over time / from other networks is not guaranteed — the
  retry below is a mitigation, not a guarantee.
- I was unable to locate and read NSE's full terms-of-service text for
  automated/API use within this session; `robots.txt` being permissive
  is not the same as confirmed ToS clearance. Review NSE's terms before
  using this in a context where that matters (e.g. production/commercial
  use at scale).
- `desc` is a short category label, not a full headline — it's used
  as-is for `title` (never invented), with `attchmntText` (NSE's own
  description text) as the summary.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx

from app.data.ingestion.news_provider import NewsProvider, NewsProviderError, RawEvent

NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements"
_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}
_IST = timezone(timedelta(hours=5, minutes=30))
_MAX_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 1.0

# NSE's `desc` field is a controlled vocabulary, not freeform text - exact
# (lowercased) matches first, then substring fallback. "other" is the
# honest default for the many administrative categories (AGM notices,
# newspaper clippings, name changes, ...) that don't fit anywhere else.
_EXACT_CATEGORY_MAP: dict[str, str] = {
    "acquisition": "ma",
    "amalgamation / merger": "ma",
    "amalgamation/merger": "ma",
    "merger": "ma",
    "dividend": "dividend",
    "buy back": "buyback",
    "buyback": "buyback",
    "bonus": "dividend",
    "allotment of securities": "fundraising",
    "allotment of equity shares": "fundraising",
    "preferential issue": "fundraising",
    "qualified institutions placement": "fundraising",
    "rights issue": "fundraising",
    "fund raising": "fundraising",
    "financial results": "earnings",
    "financial result": "earnings",
    "board meeting intimation": "earnings",
}
_SUBSTRING_CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    ("acqui", "ma"),
    ("merger", "ma"),
    ("amalgamat", "ma"),
    ("dividend", "dividend"),
    ("bonus", "dividend"),
    ("buy back", "buyback"),
    ("buyback", "buyback"),
    ("preferential", "fundraising"),
    ("rights issue", "fundraising"),
    ("qip", "fundraising"),
    ("allotment", "fundraising"),
    ("fund raising", "fundraising"),
    ("financial result", "earnings"),
    ("board meeting", "earnings"),
)


def classify_announcement_category(desc: str) -> str:
    """Best-effort category from NSE's `desc` label. Never authoritative."""
    lowered = desc.strip().lower()
    if lowered in _EXACT_CATEGORY_MAP:
        return _EXACT_CATEGORY_MAP[lowered]
    for keyword, category in _SUBSTRING_CATEGORY_RULES:
        if keyword in lowered:
            return category
    return "other"


def _parse_ist_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        naive = datetime.strptime(value.strip(), "%d-%b-%Y %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=_IST).astimezone(UTC)


def _parse_announcement(item: dict[str, Any], nse_symbol: str) -> RawEvent | None:
    desc = item.get("desc")
    if not desc or not isinstance(desc, str):
        return None

    source_url = item.get("attchmntFile")
    if not source_url or not isinstance(source_url, str):
        return None

    published_at = _parse_ist_timestamp(item.get("an_dt")) or _parse_ist_timestamp(
        item.get("exchdisstime")
    )
    if published_at is None:
        return None

    seq_id = item.get("seq_id")
    if not seq_id:
        return None

    summary = item.get("attchmntText")
    summary = summary.strip() if isinstance(summary, str) and summary.strip() else None

    return RawEvent(
        provider="nse_corporate_announcements",
        provider_event_id=str(seq_id),
        title=desc.strip(),
        category=classify_announcement_category(desc),
        summary=summary,
        published_at=published_at,
        source_name="NSE",
        source_url=source_url,
    )


class NseAnnouncementsProvider(NewsProvider):
    """News provider backed by NSE's own corporate-announcements feed."""

    def get_events(self, symbol: str, count: int = 20) -> list[RawEvent]:
        nse_symbol = symbol.strip().upper().removesuffix(".NS").removesuffix(".BO")

        last_error: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = httpx.get(
                    NSE_ANNOUNCEMENTS_URL,
                    params={"index": "equities", "symbol": nse_symbol},
                    headers=_REQUEST_HEADERS,
                    timeout=15,
                    follow_redirects=True,
                )
                response.raise_for_status()
                items = response.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_RETRY_DELAY_SECONDS)
        else:
            raise NewsProviderError(
                f"Failed to fetch NSE corporate announcements for '{symbol}' "
                f"after {_MAX_ATTEMPTS} attempts: {last_error}"
            )

        if not isinstance(items, list):
            raise NewsProviderError(f"Unexpected NSE announcements response shape for '{symbol}'.")

        events: list[RawEvent] = []
        for item in items[:count] if count else items:
            event = _parse_announcement(item, nse_symbol)
            if event is not None:
                events.append(event)
        return events
