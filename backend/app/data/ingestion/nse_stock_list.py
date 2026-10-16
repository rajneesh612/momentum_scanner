"""NIFTY 500 constituent list fetcher.

Fetches the official NSE-published NIFTY 500 constituent CSV and
normalizes it into plain dicts the stock master import can upsert. This
module only talks to NSE's static archive endpoint (or a local CSV copy
of it) — it never touches Yahoo Finance or the database, keeping
stock-universe import separate from price-history syncing.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import httpx

NIFTY_500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
_REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}


class StockListFetchError(Exception):
    """Raised when the NIFTY 500 constituent list can't be fetched or parsed."""


def fetch_nifty500(source: str | Path | None = None) -> list[dict[str, Any]]:
    """Return NIFTY 500 constituents as plain dicts.

    Each record: `symbol` (Yahoo-style, e.g. "RELIANCE.NS"), `name`,
    `sector`, `exchange` (always "NSE" — these are all NSE constituents).

    `source`, when given, is a local CSV file path with the same columns
    NSE's own export has — useful offline or if the NSE endpoint is
    unreachable. Without it, fetches live from NSE's published archive.
    """
    if source is not None:
        text = Path(source).read_text(encoding="utf-8-sig")
    else:
        try:
            response = httpx.get(
                NIFTY_500_URL, headers=_REQUEST_HEADERS, timeout=30, follow_redirects=True
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StockListFetchError(f"Failed to fetch NIFTY 500 list from NSE: {exc}") from exc
        text = response.text

    reader = csv.DictReader(io.StringIO(text))
    records: list[dict[str, Any]] = []
    for row in reader:
        symbol = (row.get("Symbol") or "").strip()
        name = (row.get("Company Name") or "").strip()
        sector = (row.get("Industry") or "").strip() or None
        if not symbol or not name:
            continue
        records.append(
            {"symbol": f"{symbol}.NS", "name": name, "sector": sector, "exchange": "NSE"}
        )

    if not records:
        raise StockListFetchError("Parsed 0 records from the NIFTY 500 source — unexpected format.")

    return records
