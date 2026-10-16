"""CLI: import/refresh the NIFTY 500 stock master list.

Run from the `backend/` directory (same place you'd run `pytest` or
`uvicorn app.main:app`), with the venv active:

    python -m scripts.import_nifty500                 # fetch live from NSE
    python -m scripts.import_nifty500 --file list.csv  # offline / manual

Idempotent — safe to re-run; it only creates stocks that don't exist yet
and updates ones whose name/sector/exchange actually changed.
"""

import argparse
import sys

from app.core.database import SessionLocal
from app.data.ingestion.nse_stock_list import StockListFetchError, fetch_nifty500
from app.services.stock_service import import_stocks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file", default=None, help="Local CSV path instead of fetching from NSE"
    )
    args = parser.parse_args()

    try:
        records = fetch_nifty500(source=args.file)
    except StockListFetchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        result = import_stocks(db, records)
    finally:
        db.close()

    print(
        f"NIFTY 500 import: {result.records_seen} seen, "
        f"{result.created} created, {result.updated} updated, {result.unchanged} unchanged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
