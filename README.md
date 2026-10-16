# Momentum Stock Scanner

A web application for scanning and ranking Indian stocks by momentum. This
repository currently implements the **project scaffold, the Market Data
Foundation** (Stock/PriceHistory persistence, a Yahoo Finance provider, and
history/sync API endpoints), **a data/chart dashboard, and a single-symbol
SMA-crossover backtester** — composite momentum scoring/ranking across many
stocks, authentication, and watchlists are not implemented yet. This README
will grow as those pieces are added.

## 1. Project Overview

Momentum Stock Scanner will eventually ingest daily price data for Indian
stocks, compute momentum indicators (moving averages, return windows,
52-week highs, relative strength, breakouts), score and rank stocks, and
present the results in a web dashboard with watchlists and charts.

Right now, the project has:

- A FastAPI backend with health-check endpoints, configuration loading, and
  a SQLAlchemy database connection.
- `Stock` and `PriceHistory` database models.
- A `YahooFinanceProvider` that fetches and normalizes daily OHLCV data.
- A `MarketDataService` and API endpoints to sync that data into PostgreSQL
  and read it back (see [Market Data API](#5-market-data-api) below).
- A `StockService` (`app/services/stock_service.py`) managing the `Stock`
  table as a searchable stock master — idempotent NIFTY 500 import
  (`backend/scripts/import_nifty500.py`, sourced live from NSE's own
  published constituent list) plus a `GET /api/v1/stocks` search/filter/
  pagination endpoint, separate from price-history syncing.
- A framework-free SMA-crossover backtest engine (`app/momentum/backtest.py`)
  and a `POST /api/v1/backtest/{symbol}` endpoint that runs it against
  synced price history.
- A React + TypeScript + Vite frontend with a searchable stock combobox
  (symbol or company name, backed by `GET /api/v1/stocks`) used on both
  tabs instead of free-text symbol entry, a Data tab (sync a symbol, view
  its price/volume chart and history table) and a Backtest tab (configure
  and run the SMA-crossover strategy, view the equity curve vs. buy-and-hold
  and the resulting trade list).
- A PostgreSQL database via Docker Compose.

## 2. Architecture

The intended data/control flow, once fully built out:

```
Market Data Provider (e.g. Yahoo Finance)
        │
        ▼
  Data Ingestion  ───────────►  PostgreSQL
        │                            │
        ▼                            ▼
  Data Processing  ◄───────────  (reads)
        │
        ▼
  Momentum Engine
        │
        ▼
     FastAPI  ◄── database layer (no business logic)
        │
        ▼
  React Dashboard
```

Design principles enforced by the folder structure:

- **The market data provider is replaceable.** `app/data/ingestion/provider.py`
  defines a `MarketDataProvider` abstract interface; `yahoo_finance.py`
  provides a `YahooFinanceProvider` implementation. Swapping providers later
  should not require changes outside `app/data/ingestion/`.
- **The momentum engine does not depend on FastAPI.** `app/momentum/`
  modules operate on plain data structures (e.g. pandas DataFrames) so they
  stay independently testable and reusable outside the API.
- **The database layer contains no business logic.** `app/core/database.py`
  only sets up the SQLAlchemy engine, session, and declarative base.
- **The frontend never talks to yfinance (or any provider) directly.** It
  only calls the FastAPI backend, via `frontend/src/services/`.
- API routes (`app/api/`) stay thin and delegate to `app/services/` for
  business logic — routes should not contain it directly.
- Database models (`app/models/`) are kept separate from API request/response
  schemas (`app/schemas/`).

## 3. Technology Stack

**Backend**

- Python 3.12+
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL
- Pydantic v2 / Pydantic Settings
- Uvicorn
- Pandas / NumPy
- yfinance
- Pytest
- Ruff

**Frontend**

- React 19
- TypeScript
- Vite
- Tailwind CSS v4

**Infrastructure**

- Docker Compose (PostgreSQL only, for now)

## 4. Project Structure

```
momentum-stock-scanner/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py                # Shared FastAPI dependencies
│   │   │   ├── __init__.py
│   │   │   └── routes/
│   │   │       ├── __init__.py
│   │   │       ├── health.py          # / and /health endpoints
│   │   │       ├── stocks.py          # GET /stocks, GET /stocks/{symbol}/history
│   │   │       ├── market_data.py     # POST /market-data/sync/{symbol}
│   │   │       └── backtest.py        # POST /backtest/{symbol}
│   │   │
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic Settings
│   │   │   └── database.py            # SQLAlchemy engine/session/Base
│   │   │
│   │   ├── models/
│   │   │   ├── stock.py               # Stock ORM model
│   │   │   └── price_history.py       # PriceHistory ORM model
│   │   ├── schemas/
│   │   │   ├── stock.py               # StockRead, StockListResponse
│   │   │   ├── price_history.py       # PriceHistoryRead
│   │   │   ├── market_data.py         # HistoricalPriceResponse, MarketDataSyncResponse
│   │   │   └── backtest.py            # BacktestResponse and friends
│   │   ├── services/
│   │   │   ├── market_data_service.py # MarketDataService (price fetch + persist)
│   │   │   ├── stock_service.py       # Stock master: import_stocks, list_stocks
│   │   │   └── backtest_service.py    # Bridges PriceHistory -> the backtest engine
│   │   │
│   │   ├── data/
│   │   │   ├── ingestion/
│   │   │   │   ├── provider.py        # MarketDataProvider interface + shared errors
│   │   │   │   ├── yahoo_finance.py   # YahooFinanceProvider (implemented)
│   │   │   │   └── nse_stock_list.py  # NIFTY 500 constituent fetcher
│   │   │   └── processing/            # Raw-data -> analysis-ready transforms
│   │   │
│   │   ├── momentum/
│   │   │   ├── indicators.py          # Placeholder
│   │   │   ├── scoring.py             # Placeholder
│   │   │   ├── ranking.py             # Placeholder
│   │   │   └── backtest.py            # SMA-crossover backtest engine (implemented)
│   │   │
│   │   └── main.py                    # FastAPI app entry point
│   │
│   ├── scripts/
│   │   └── import_nifty500.py         # CLI: idempotent stock-master import
│   ├── tests/
│   ├── requirements.txt
│   ├── pyproject.toml                 # Ruff + Pytest config
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── StockCombobox.tsx      # Searchable symbol/company picker
│   │   │   ├── PriceChart.tsx, EquityCurveChart.tsx, PriceHistoryTable.tsx, TradesTable.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx          # Data tab: sync + chart + history
│   │   │   └── Backtest.tsx           # Backtest tab
│   │   ├── services/
│   │   │   └── api.ts                 # Backend API client
│   │   ├── hooks/                     # Custom hooks (empty for now)
│   │   ├── types/
│   │   │   └── index.ts               # Shared TS types
│   │   ├── utils/                     # Helpers (empty for now)
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
│
├── scripts/                           # Future dev/ops scripts
├── docs/                              # Future documentation
├── docker-compose.yml                 # PostgreSQL only
├── .gitignore
└── README.md
```

## 5. Stock & Market Data API

Four endpoints are implemented so far, under the `/api/v1` prefix.

### `GET /api/v1/stocks`

Searches/lists the stock master (the `Stock` table) — used to populate a
symbol picker. Reads from PostgreSQL only; never calls Yahoo Finance.

Query params: `q` (matches symbol or company name, case-insensitive
substring), `is_active` (default `true`), `limit` (default `50`, max
`200`), `offset` (default `0`). Results are sorted stably by `symbol`.

```bash
curl "http://localhost:8000/api/v1/stocks?q=reliance&limit=10"
```

```json
{
  "items": [
    {
      "id": 12,
      "symbol": "RELIANCE.NS",
      "name": "Reliance Industries Ltd.",
      "exchange": "NSE",
      "sector": "Oil Gas & Consumable Fuels",
      "is_active": true,
      "created_at": "2026-10-16T10:00:00Z",
      "updated_at": "2026-10-16T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

The `Stock` table is populated via the import script below, or lazily by
`POST /market-data/sync/{symbol}` if a symbol is synced before it's ever
been imported.

### `POST /api/v1/market-data/sync/{symbol}`

Fetches historical OHLCV data for `symbol` from Yahoo Finance and persists
it into PostgreSQL (creating the `Stock` row if needed). Duplicate
`(stock_id, date, interval)` records are skipped, not re-inserted.

Optional query params: `start_date`, `end_date` (default: last 365 days),
`interval` (default: `1d`).

```bash
curl -X POST "http://localhost:8000/api/v1/market-data/sync/RELIANCE.NS?start_date=2016-01-01&end_date=2026-01-31&interval=1wk"
```

```json
{
  "symbol": "RELIANCE.NS",
  "interval": "1wk",
  "start_date": "2016-01-01",
  "end_date": "2026-01-31",
  "records_fetched": 522,
  "records_created": 522,
  "records_skipped": 0
}
```

### `GET /api/v1/stocks/{symbol}/history`

Returns previously-synced price history for `symbol` from PostgreSQL — it
does not call Yahoo Finance. Required query params: `start_date`, `end_date`.
Optional: `interval` (default: `1d`) — only rows synced at that interval
are returned.

```bash
curl "http://localhost:8000/api/v1/stocks/RELIANCE.NS/history?start_date=2024-01-01&end_date=2024-01-31"
```

```json
{
  "symbol": "RELIANCE.NS",
  "exchange": "NSE",
  "interval": "1d",
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "count": 1,
  "prices": [
    {
      "date": "2024-01-02",
      "interval": "1d",
      "open": 100.0,
      "high": 105.0,
      "low": 99.0,
      "close": 104.0,
      "adjusted_close": 103.5,
      "volume": 1000000
    }
  ]
}
```

### `POST /api/v1/backtest/{symbol}`

Runs a long-only SMA-crossover backtest against previously-synced price
history in PostgreSQL — like the history endpoint, it never calls Yahoo
Finance, so `symbol` must already be synced for the requested range (plus
enough lookback before `start_date` for the long SMA to warm up — e.g. sync
2+ years of history for the SMA(50)/SMA(200) defaults).

The strategy goes long the bar the short SMA crosses above the long SMA,
and exits the bar it crosses back below (one position at a time, no
shorting, no transaction costs).

Query params: `start_date`, `end_date` (required); `interval` (default
`1d`); `short_window` (default `50`), `long_window` (default `200` — these
are bar counts at whatever `interval` you pick, e.g. 10/40 weeks or 3/12
months read very differently from 10/40 days), `initial_capital` (default
`100000`).

```bash
curl -X POST "http://localhost:8000/api/v1/backtest/TCS.NS?start_date=2018-01-01&end_date=2026-09-21&interval=1wk&short_window=10&long_window=40&initial_capital=100000"
```

```json
{
  "symbol": "TCS.NS",
  "exchange": "NSE",
  "strategy": "sma_crossover",
  "interval": "1wk",
  "short_window": 10,
  "long_window": 40,
  "start_date": "2018-01-01",
  "end_date": "2026-09-21",
  "lookback_bars": 47,
  "summary": {
    "initial_capital": 100000.0,
    "final_equity": 177994.69,
    "total_return_pct": 77.99,
    "buy_and_hold_return_pct": 56.55,
    "cagr_pct": 6.85,
    "max_drawdown_pct": -30.22,
    "num_trades": 9,
    "win_rate_pct": 66.67
  },
  "equity_curve": [
    { "date": "2018-01-05", "close": 1601.05, "equity": 100000.0, "in_position": false }
  ],
  "trades": [
    {
      "entry_date": "2018-03-09",
      "entry_price": 1516.6,
      "exit_date": "2018-11-02",
      "exit_price": 1830.1,
      "return_pct": 20.67,
      "holding_days": 238,
      "is_open": false
    }
  ]
}
```

`lookback_bars` is how many synced rows existed before `start_date` — if
it's less than `long_window - 1`, the long SMA hasn't fully warmed up at
the start of the window and the strategy stays flat until it does.

### Error responses

| Scenario                                   | Status |
| ------------------------------------------- | ------ |
| `start_date` after `end_date`               | 400    |
| `interval` not one of `1d`, `1wk`, `1mo`     | 400    |
| `short_window` >= `long_window`, or either non-positive | 400 |
| `initial_capital` <= 0                      | 400    |
| Symbol not found (sync) / never synced (history, backtest) | 404 |
| No data for the requested range             | 404    |
| Yahoo Finance provider failure               | 502    |
| Database write failure during sync           | 503    |
| Missing/invalid query params, or `/stocks` `limit`/`offset` out of range | 422 |

No results for `GET /api/v1/stocks` (e.g. no match for `q`) returns `200`
with `"items": []` — it's a collection endpoint, not a single-resource
lookup, so an empty result isn't an error.

### Importing the stock master

```bash
cd backend
.venv\Scripts\python.exe -m scripts.import_nifty500
```

Idempotent — safe to re-run. Fetches NSE's own published NIFTY 500
constituent list live (`https://nsearchives.nseindia.com/content/indices/
ind_nifty500list.csv`), upserts into `Stock` keyed on `symbol`. Use
`--file path/to/list.csv` to import from a local CSV (same columns as
NSE's export) instead of fetching live — useful if that endpoint is
unreachable from your network, or offline.

This covers the NIFTY 500, not the full NSE universe — there's no equally
reliable single published source for that; a complete-NSE import would
need a different (and less officially-maintained) data source.

## 6. Local Setup

Prerequisites:

- Python 3.12+
- Node.js 20+
- Docker Desktop (for PostgreSQL)

Clone the repository, then set up the backend and frontend as described
below.

## 7. PostgreSQL Setup

Start PostgreSQL via Docker Compose from the repository root:

```bash
docker compose up -d
```

This starts a `postgres:16-alpine` container using the environment
variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, and
`POSTGRES_PORT` (all optional — sensible defaults are provided, see
`docker-compose.yml`). Data persists in a named Docker volume.

To stop it:

```bash
docker compose down
```

## 8. Backend Startup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# edit .env if your database credentials differ from the defaults

uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`, with interactive
Swagger docs at `http://localhost:8000/docs`.

## 9. Frontend Startup

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The app will be available at `http://localhost:5173`.

## 10. Running Tests

Backend:

```bash
cd backend
pytest
```

Tests never make real Yahoo Finance network calls — `YahooFinanceProvider`
is either mocked directly or swapped for a `FakeMarketDataProvider` via
FastAPI dependency overrides (`app.dependency_overrides`), and database
tests run against an isolated in-memory SQLite database rather than
PostgreSQL.

## 11. Environment Variables

**Backend** (`backend/.env`, see `backend/.env.example`):

| Variable       | Description                              | Default (dev)                                                      |
| -------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| `APP_NAME`     | Application display name                  | `Momentum Stock Scanner`                                             |
| `APP_ENV`      | Environment name (`development`, `production`, ...) | `development`                                             |
| `LOG_LEVEL`    | Logging level                             | `INFO`                                                                |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string   | `postgresql+psycopg2://postgres:postgres@localhost:5432/momentum_stock_scanner` |
| `CORS_ORIGINS` | JSON list of allowed frontend origins     | `["http://localhost:5173"]`                                          |

**Frontend** (`frontend/.env`, see `frontend/.env.example`):

| Variable              | Description             | Default (dev)           |
| --------------------- | ------------------------ | ------------------------ |
| `VITE_API_BASE_URL`   | Backend API base URL     | `http://localhost:8000` |

**Docker Compose** (optional overrides, exported in your shell or via a
root `.env` file):

| Variable            | Description             | Default                    |
| -------------------- | ------------------------ | --------------------------- |
| `POSTGRES_USER`      | PostgreSQL username      | `postgres`                  |
| `POSTGRES_PASSWORD`  | PostgreSQL password      | `postgres`                  |
| `POSTGRES_DB`        | PostgreSQL database name | `momentum_stock_scanner`    |
| `POSTGRES_PORT`      | Host port to expose      | `5432`                      |

No secrets are hardcoded or committed anywhere in this repository.

## 12. Future Development Roadmap

The Market Data Foundation (`Stock`/`PriceHistory` models, Yahoo Finance
ingestion, sync/history endpoints), the Data/Backtest frontend, a
single-symbol SMA-crossover backtest engine, and a searchable NIFTY 500
stock master (import + `GET /api/v1/stocks` + frontend combobox) are done.
Still to be built incrementally:

1. Alembic migrations (tables are currently created ad hoc / via
   `Base.metadata.create_all()` in tests — no migration tooling yet).
2. Full-NSE stock master coverage (today's import is NIFTY 500 only — see
   [Importing the stock master](#importing-the-stock-master) — there's no
   equally reliable single published source for the complete NSE list).
3. Database models for `momentum_scores`, `watchlists`, `users`,
   `market_indices`.
4. Data processing pipelines (raw prices -> clean, analysis-ready series).
5. Composite momentum indicators/scoring/ranking across many stocks
   (`app/momentum/indicators.py` and `scoring.py` are still placeholders;
   `backtest.py` only computes the SMAs it needs for itself). Additional
   backtest strategies (return-threshold, breakout) beyond SMA crossover.
6. API endpoints exposing momentum rankings and watchlists.
7. Frontend pages/components: momentum ranking table, watchlist management.
8. Authentication and user accounts.
9. Notifications / alerts.
10. Production deployment configuration.
