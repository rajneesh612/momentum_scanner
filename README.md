# Momentum Stock Scanner

A web application for scanning and ranking Indian stocks by momentum. This
repository currently implements the **project scaffold, the Market Data
Foundation** (Stock/PriceHistory persistence, a Yahoo Finance provider, and
history/sync API endpoints), **a data/chart dashboard, a single-symbol
SMA-crossover backtester, a news/corporate-event layer, and a daily NIFTY 500
hybrid trend/momentum/volume signal scanner with Telegram alerts** —
composite momentum scoring/ranking across many stocks, authentication, and
watchlists are not implemented yet. This README will grow as those pieces
are added.

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
- A daily **NIFTY 500 hybrid signal scanner** (`app/momentum/hybrid_signal.py`
  + `app/services/scan_service.py`) that evaluates a configurable
  trend/momentum/volume strategy against completed daily candles, persists
  BUY/SELL transitions (`SignalEvent`), and sends Telegram alerts — see
  [Daily Hybrid Signal Scanner](#12-daily-hybrid-signal-scanner) below.
- Alembic migrations (`backend/migrations/`) for every table, including the
  two tables that predate Alembic being introduced into this project.

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
- APScheduler (daily scan scheduling)
- Alembic (database migrations)
- httpx (Telegram Bot API calls)
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
│   │   │       ├── backtest.py        # POST /backtest/{symbol}
│   │   │       ├── events.py          # News/corporate-event endpoints
│   │   │       └── signals.py         # Scanner: signals, scans, manual trigger, Telegram test
│   │   │
│   │   ├── core/
│   │   │   ├── config.py              # Pydantic Settings
│   │   │   └── database.py            # SQLAlchemy engine/session/Base
│   │   │
│   │   ├── models/
│   │   │   ├── stock.py               # Stock ORM model
│   │   │   ├── price_history.py       # PriceHistory ORM model
│   │   │   ├── stock_event.py         # StockEvent ORM model
│   │   │   ├── signal_event.py        # SignalEvent (BUY/SELL transitions)
│   │   │   ├── scan_run.py            # ScanRun (scan audit trail)
│   │   │   ├── notification_delivery.py # NotificationDelivery (Telegram attempts)
│   │   │   ├── scan_lock.py           # ScanLock (DB-backed mutex)
│   │   │   ├── universe_membership.py # UniverseMembershipEvent (add/remove history)
│   │   │   └── strategy_config.py     # StrategyConfigVersion (config audit log)
│   │   ├── schemas/
│   │   │   ├── stock.py               # StockRead, StockListResponse
│   │   │   ├── price_history.py       # PriceHistoryRead
│   │   │   ├── market_data.py         # HistoricalPriceResponse, MarketDataSyncResponse
│   │   │   ├── backtest.py            # BacktestResponse and friends
│   │   │   └── signal.py              # SignalEventRead, ScanRunRead, HybridBacktestResponse, ...
│   │   ├── services/
│   │   │   ├── market_data_service.py # MarketDataService (price fetch + persist)
│   │   │   ├── stock_service.py       # Stock master: import_stocks, list_stocks
│   │   │   ├── backtest_service.py    # Bridges PriceHistory -> the SMA backtest engine
│   │   │   ├── universe_service.py    # NIFTY 500 universe refresh/deactivation/history
│   │   │   ├── signal_service.py      # Per-symbol hybrid-signal evaluation + persistence
│   │   │   ├── scan_service.py        # Full-universe scan orchestration
│   │   │   ├── scan_lock_service.py   # DB-backed mutex (prevents concurrent scans)
│   │   │   ├── telegram_service.py    # Telegram Bot API delivery (retry/backoff)
│   │   │   ├── notification_service.py # Formats + idempotently delivers notifications
│   │   │   └── trading_calendar.py    # Weekday-based "latest completed session" helper
│   │   │
│   │   ├── data/
│   │   │   ├── ingestion/
│   │   │   │   ├── provider.py        # MarketDataProvider interface + shared errors
│   │   │   │   ├── yahoo_finance.py   # YahooFinanceProvider (implemented)
│   │   │   │   ├── nse_stock_list.py  # NIFTY 500 constituent fetcher
│   │   │   │   ├── news_provider.py   # NewsProvider interface
│   │   │   │   └── nse_announcements.py # NseAnnouncementsProvider (implemented)
│   │   │   └── processing/            # Raw-data -> analysis-ready transforms
│   │   │
│   │   ├── momentum/
│   │   │   ├── indicators.py          # Placeholder
│   │   │   ├── scoring.py             # Placeholder
│   │   │   ├── ranking.py             # Placeholder
│   │   │   ├── backtest.py            # SMA-crossover backtest engine (implemented)
│   │   │   ├── event_impact.py        # Post-event return-window analysis
│   │   │   └── hybrid_signal.py       # Hybrid trend/momentum/volume engine + backtest
│   │   │
│   │   ├── scheduler.py               # APScheduler: daily scan, Asia/Kolkata cron
│   │   └── main.py                    # FastAPI app entry point
│   │
│   ├── migrations/                    # Alembic migrations
│   │   ├── env.py                     # Reads DATABASE_URL from Settings, not a 2nd config
│   │   └── versions/
│   │       ├── 0001_baseline_*.py     # stocks/price_history/stock_events (pre-Alembic tables)
│   │       └── 0002_scanner_tables_*.py # every scanner table
│   ├── scripts/
│   │   └── import_nifty500.py         # CLI: idempotent stock-master import
│   ├── tests/
│   ├── alembic.ini
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

Tests never make real Yahoo Finance, NSE, or Telegram network calls —
providers are either mocked directly (`unittest.mock.patch`) or swapped for
fakes (`FakeMarketDataProvider`, `FakeNewsProvider`) via FastAPI dependency
overrides (`app.dependency_overrides`), and database tests run against an
isolated in-memory SQLite database rather than PostgreSQL. Scan-orchestration
tests (`test_scan_service.py`) monkeypatch `SessionLocal` to point worker
threads at that same SQLite engine instead of a real Postgres connection
pool.

To also run a manual scan against the real stack: `cd backend && python -m scripts.import_nifty500`
first (so there's a universe to scan), then see
[Daily Hybrid Signal Scanner](#12-daily-hybrid-signal-scanner) for the
`POST /api/v1/scans/run` command.

## 11. Environment Variables

**Backend** (`backend/.env`, see `backend/.env.example`):

| Variable       | Description                              | Default (dev)                                                      |
| -------------- | ----------------------------------------- | -------------------------------------------------------------------- |
| `APP_NAME`     | Application display name                  | `Momentum Stock Scanner`                                             |
| `APP_ENV`      | Environment name (`development`, `production`, ...) | `development`                                             |
| `LOG_LEVEL`    | Logging level                             | `INFO`                                                                |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string   | `postgresql+psycopg2://postgres:postgres@localhost:5432/momentum_stock_scanner` |
| `CORS_ORIGINS` | JSON list of allowed frontend origins     | `["http://localhost:5173"]`                                          |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (see setup below) | *(blank)*                                                       |
| `TELEGRAM_CHAT_ID`   | Telegram chat id to send alerts to   | *(blank)*                                                       |
| `TELEGRAM_ALERTS_ENABLED` | Master on/off switch for Telegram alerts | `false`                                                 |
| `TELEGRAM_MAX_NOTIFICATIONS_PER_SCAN` | Cap on alerts sent per scan run | `20`                                              |
| `SCHEDULER_ENABLED`  | Run the daily scan automatically      | `false`                                                         |
| `SCHEDULER_TIMEZONE` | Timezone for the scan schedule        | `Asia/Kolkata`                                                  |
| `SCAN_POST_CLOSE_DELAY_MINUTES` | Informational buffer after NSE close | `45`                                                     |
| `SCAN_HOUR_IST` / `SCAN_MINUTE_IST` | Daily scan time (IST, 24h)    | `16` / `15`                                              |
| `SCAN_API_KEY`       | Required to call manual-trigger/test/refresh endpoints | *(blank = disabled)*                       |
| `SCAN_MAX_CONCURRENT_SYMBOLS` | Per-scan symbol fetch concurrency | `5`                                                      |
| `SCAN_MAX_RETRIES` / `SCAN_RETRY_BACKOFF_SECONDS` | Per-symbol fetch retry policy | `3` / `2.0`                                  |

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

## 12. Daily Hybrid Signal Scanner

A daily end-of-day scanner over the NIFTY 500 universe: a configurable
trend/momentum/volume strategy evaluated once per completed session,
BUY/SELL transitions persisted and deduplicated, and (optionally) pushed to
Telegram. This is a **research and decision-support tool, not an automated
order-execution system** — nothing in this project places a live trade.

### Strategy (baseline, configurable via `HybridStrategyConfig`)

Computed from `adjusted_close` only (never mixed with unadjusted OHLC —
avoids a split/bonus masquerading as a crash or rally). A rolling
close-to-close stdev stands in for ATR (`volatility_pct`, informational
only — true ATR needs split-adjusted high/low, which this project does not
store).

**BUY-eligible** when, on the latest *completed* session, all hold:
close > SMA50, SMA50 > SMA200, 20-session return > 0, ~12-month
(252-session) return > 0, and volume > 1.2× its 20-session average. A BUY
signal fires only on the transition from ineligible → eligible — not every
day the conditions keep holding.

**SELL/exit** when, while in a position: close < SMA50, or SMA50 < SMA200.

**Data quality**, always one of `ok` / `insufficient` (not enough history
yet) / `stale` (latest bar is older than the session, within tolerance) /
`missing` (nothing usable at all) — a signal is only ever generated on
`ok`. See `app/momentum/hybrid_signal.py` for the full engine (also unit
tested — `backend/tests/test_hybrid_signal.py`).

### No look-ahead bias

Live scanning only ever evaluates a session once the scheduler's
post-close delay has passed (`app/services/trading_calendar.py`), and only
reads bars at/before that session. The backtester (below) confirms a
signal using the signal bar's own close, then **fills at the next
session's close**, never the signal bar itself — covered by
`test_hybrid_backtest_executes_on_next_bar_not_signal_bar`.

### State durability & deduplication

Whether a stock is "currently in a BUY position" is derived by reading the
**most recent persisted `SignalEvent`** for that stock+strategy — never
from an in-memory variable — so a backend restart or a second worker
process always agrees on state. A DB unique constraint on
`(stock_id, strategy_name, strategy_version, session_date, signal_type)` is
a second-layer backstop against two concurrent scans racing on the same
session (the loser's insert fails the constraint and is treated as
"already recorded", not an error).

### Universe management

`POST /api/v1/universe/refresh` (reuses `app/data/ingestion/nse_stock_list.py`
and `Stock.is_active`) fetches the live NIFTY 500 list, activates new
symbols, and **deactivates** (never deletes) symbols that dropped out —
every add/remove is logged to `UniverseMembershipEvent` for a partial
survivorship-bias mitigation. If the NSE fetch fails, the existing universe
is left completely untouched (never replaced with an empty/partial list).
Universe refresh is a separate operation from scanning — a scan always
runs against whatever universe was last successfully imported.

### Scheduling

`app/scheduler.py` runs the scan on weekdays at `SCAN_HOUR_IST:SCAN_MINUTE_IST`
(`Asia/Kolkata`, default `16:15` — NSE closes `15:30` + a configurable
post-close delay). It does **not** model NSE holidays — a scan on a holiday
just finds stale data and reports it honestly, rather than fabricating a
signal. A DB-backed lock (`scan_lock_service.py`, works the same on SQLite
and Postgres) prevents two workers/processes from scanning concurrently;
the loser gets `ScanLockHeldError`, logged and skipped, not escalated.
Disabled by default (`SCHEDULER_ENABLED=false`) — enable it for a real
deployment; in local dev, use the manual-trigger endpoint instead of
leaving it on.

**Local dev vs. production**: `SCHEDULER_ENABLED=true` starts an
in-process `BackgroundScheduler` for as long as the `uvicorn` process is
running — fine for a single long-running dev/staging process, but if this
app is deployed to a platform that sleeps or restarts the process (e.g. a
serverless/scale-to-zero host), the scheduler will miss runs while asleep.
On such a platform, run the scan via an external scheduled trigger (e.g. a
cron-triggered call to `POST /api/v1/scans/run`) instead of relying on the
in-process scheduler.

### Telegram alerts

Uses the Telegram Bot API directly over HTTPS (`app/services/telegram_service.py`),
with bounded retries/backoff on timeouts/429/5xx, and never marks a
notification `sent` until Telegram's response confirms `ok: true`. A
network timeout *after* Telegram already queued the message is a known,
disclosed edge case where a duplicate message can occur — this is not
hidden, and exactly-once delivery is not claimed.

**Setup:**

1. Message [@BotFather](https://core.telegram.org/bots#6-botfather) on
   Telegram, `/newbot`, follow the prompts — it gives you a bot token.
2. Send your new bot any message (so it has a chat to reply into).
3. Fetch your chat id:
   `curl https://api.telegram.org/bot<TOKEN>/getUpdates` and read
   `result[0].message.chat.id` from the response.
4. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALERTS_ENABLED=true`
   in `backend/.env`.
5. Verify: `curl -X POST "http://localhost:8000/api/v1/telegram/test" -H "X-Scan-Api-Key: <your SCAN_API_KEY>"`
   — sends a plain test message, never a fabricated BUY/SELL signal.

A SELL message means "exit per this strategy", not "this stock is bad" or
a short-sell recommendation — the message text says so explicitly.

### Database migrations

```bash
cd backend
# Fresh database (nothing created yet):
alembic upgrade head

# A database that already has stocks/price_history/stock_events from
# before Alembic was introduced (e.g. this project's existing dev DB):
alembic stamp 0001_baseline
alembic upgrade head   # applies only 0002_scanner_tables
```

`migrations/env.py` reads the same `DATABASE_URL` the app itself uses
(via `Settings`) — there is no second, independently-maintained connection
string in `alembic.ini`.

### API endpoints

| Endpoint | Notes |
| --- | --- |
| `GET /api/v1/strategy-config` | Current `HybridStrategyConfig` values. |
| `GET /api/v1/signals/latest` | Most recent signals across all symbols. |
| `GET /api/v1/signals` | Filterable by `symbol`, `signal_type`, date range. |
| `GET /api/v1/scans/latest` | Most recent scan run (404 if none yet). |
| `GET /api/v1/scans` | Scan-run history. |
| `POST /api/v1/scans/run` | Manual trigger — **requires `X-Scan-Api-Key`**. |
| `POST /api/v1/telegram/test` | Plain test message — **requires `X-Scan-Api-Key`**. |
| `POST /api/v1/universe/refresh` | Refresh NIFTY 500 list — **requires `X-Scan-Api-Key`**. |
| `POST /api/v1/backtest/hybrid/{symbol}` | Backtests the *same* strategy code the live scanner runs. |

`X-Scan-Api-Key`-protected endpoints return `503` if `SCAN_API_KEY` isn't
configured at all, `401` on a wrong/missing header.

### Known limitations

- No real NSE trading-holiday calendar (weekday-only).
- `adjusted_close`-only volatility proxy, not true ATR.
- Universe history starts from whenever refreshes began running in this
  deployment — no historical point-in-time NIFTY 500 constituent data
  exists to backfill from, so a backtest run today still uses *today's*
  universe membership for any past date (a labeled, not hidden,
  survivorship-bias limitation).
- Backtest cost model is a single flat round-trip `cost_bps`, not a full
  brokerage/STT/stamp-duty breakdown.
- Sharpe ratio uses a 0% risk-free rate, not a real T-bill yield.
- Telegram delivery is best-effort retried, not exactly-once.

## 13. Future Development Roadmap

The Market Data Foundation (`Stock`/`PriceHistory` models, Yahoo Finance
ingestion, sync/history endpoints), the Data/Backtest frontend, a
single-symbol SMA-crossover backtest engine, a searchable NIFTY 500 stock
master (import + `GET /api/v1/stocks` + frontend combobox), a news/
corporate-event layer, Alembic migrations, and the daily hybrid signal
scanner with Telegram alerts (see
[Daily Hybrid Signal Scanner](#12-daily-hybrid-signal-scanner)) are done.
Still to be built incrementally:

1. Full-NSE stock master coverage (today's import is NIFTY 500 only — see
   [Importing the stock master](#importing-the-stock-master) — there's no
   equally reliable single published source for the complete NSE list).
2. Database models for `momentum_scores`, `watchlists`, `users`,
   `market_indices`.
3. Data processing pipelines (raw prices -> clean, analysis-ready series).
4. Composite momentum indicators/scoring/ranking across many stocks
   (`app/momentum/indicators.py` and `scoring.py` are still placeholders;
   the SMA and hybrid backtest engines each only compute the indicators
   they need for themselves). Additional backtest strategies beyond SMA
   crossover and the hybrid strategy.
5. API endpoints exposing momentum rankings and watchlists.
6. Frontend pages/components: momentum ranking table, watchlist management.
7. Authentication and user accounts (including securing the scanner's
   manual-trigger endpoints beyond a single shared `SCAN_API_KEY`).
8. A real NSE trading-holiday calendar for the scheduler (currently
   weekday-only — see [Known limitations](#known-limitations)).
9. Production deployment configuration (process manager/supervisor for
   the scheduler, secrets management for `TELEGRAM_BOT_TOKEN`/`SCAN_API_KEY`).
