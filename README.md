# CerebralZip — E-Commerce Sales Analytics Chatbot

A Data Science Internship assignment for CerebralZip: a chatbot that answers plain-English
analytics questions about the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/olistbr/brazilian-ecommerce),
via an LLM (or rule-based fallback) agent that calls controlled MCP tools rather than
running arbitrary SQL.

## Architecture

```
Frontend
    ↓
FastAPI API
    ↓
ILLMAgent interface
    ├── LLMAgent        (Groq-backed, decides which MCP tools to call)
    └── FallbackAgent    (rule-based, works without an LLM)
    ↓
MCP Server (official Python MCP SDK)
    ↓
Analytics MCP Tools (orders, products, sellers, reviews, payments, delivery)
    ↓
SQLite Database (Olist dataset)
```

Design principles:

- The API and dashboard depend only on the `ILLMAgent` interface, never on `LLMAgent` or
  `FallbackAgent` directly, so `AGENT_MODE` can switch implementations with no other code
  changes.
- The LLM never executes SQL directly. All data access goes through controlled MCP tools.
- The database layer is independent of the API/agent layers.
- Chart selection and refresh-comparison logic live in `app/analytics/`, separate from the
  MCP/database layer.

## Tech stack

- Python 3.11, FastAPI
- Official Python MCP SDK (`mcp`)
- SQLite + pandas
- Groq API (LLM agent)
- React + Vite + Chart.js (frontend)
- Docker / Docker Compose
- pytest

## Project structure

```
cerebralzip-analytics/
├── app/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── api/                     # HTTP routes
│   ├── agent/                   # ILLMAgent interface + implementations
│   ├── mcp_server/               # MCP server + analytics tools
│   ├── analytics/                # Chart selection, insight, refresh comparison
│   ├── database/                 # SQLite connection, models, loader
│   └── schemas/                  # Pydantic request/response models
├── frontend/                     # Basic React + Vite app
├── data/                         # Olist CSVs / SQLite DB live here at runtime
├── tests/                        # pytest tests
├── .env.example
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Environment variables

Copy `.env.example` to `.env` and fill in values as needed. **Never commit `.env`** — it is
git-ignored.

| Variable | Description |
|---|---|
| `AGENT_MODE` | `llm` or `fallback` — selects which `ILLMAgent` implementation is used. |
| `GROQ_API_KEY` | API key for the Groq LLM (leave blank if using `fallback` mode). |
| `LLM_MODEL` | Groq model name for the LLM agent. |
| `LLM_TIMEOUT_SECONDS` | Timeout before falling back if the LLM is slow. |
| `DATABASE_PATH` | Path to the SQLite database file inside the container. |
| `API_HOST` / `API_PORT` | FastAPI bind host/port. |

## Setup (local, without Docker)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Then visit `http://localhost:8000/health`.

## Setup (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

This starts the backend on `http://localhost:8000` and the basic Vite frontend on
`http://localhost:5173`. The backend health endpoint at `http://localhost:8000/health`
should return:

```json
{"status": "ok"}
```

## Running tests

```bash
pytest
```

## Step 1 — Dataset & Database

The Step 1 scope established the dataset-to-SQLite foundation used by the later MCP,
agent, analytics, dashboard, and frontend layers.

### Dataset and commands

The source is the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/olistbr/brazilian-ecommerce).
Place its nine CSV files in `data/`:

`olist_customers_dataset.csv`, `olist_geolocation_dataset.csv`, `olist_orders_dataset.csv`,
`olist_order_items_dataset.csv`, `olist_order_payments_dataset.csv`,
`olist_order_reviews_dataset.csv`, `olist_products_dataset.csv`, `olist_sellers_dataset.csv`,
and `product_category_name_translation.csv`.

Run the explicit, repeatable database workflow from the repository root:

```bash
python scripts/inspect_dataset.py
python scripts/load_database.py
python scripts/validate_database.py
pytest
```

The loader uses `DATABASE_PATH` when set and defaults to `data/olist.db`. It drops and
recreates analytical tables on an explicit reload; API startup does not load CSVs.
SQLite stores timestamps as ISO-compatible `TEXT` values (`YYYY-MM-DDTHH:MM:SS`).

### Schema and data decisions

The schema contains `customers`, `geolocation`, `orders`, `order_items`,
`order_payments`, `order_reviews`, `products`, `sellers`, and
`product_category_name_translation`. Orders reference customers; items reference orders,
products, and sellers; payments and reviews reference orders. Customer and seller ZIP
prefixes join to geolocation, which intentionally has no unique ZIP constraint because a
prefix maps to multiple rows. Reviews use a surrogate row key because `review_id` is not
unique. Items and payments use composite primary keys.

Product categories are returned through an explicit join from `products` to
`product_category_name_translation`; product category names are not silently renamed.
Untranslated product categories remain nullable/unmatched and are reported by inspection.
Indexes cover order/customer/date access, item product/seller access, category access,
ZIP lookups, and order child tables. Foreign-key enforcement is enabled per connection.

The generated SQLite database and downloaded CSV files are ignored by Git. Tests use tiny
temporary CSV fixtures; the inspection, loading, and validation commands exercise the real
dataset.

## Step 0 foundation

## Step 3 — Agent Layer

The agent layer now exposes one asynchronous contract:
`ILLMAgent.analyze(question) -> dict`. `get_agent()` selects `LLMAgent` or
`FallbackAgent` from `AGENT_MODE`, so callers do not branch on the active mode.
`answer_query()` remains as a compatibility alias for the earlier Step 0 name.

`LLMAgent` uses the configured Groq client and native function calling. The model sees
only the six existing Step 2 analytics tools and their structured schemas; it cannot
write SQL or access an arbitrary SQL tool. Tool calls are dispatched through the existing
domain functions, bounded by `LLM_TIMEOUT_SECONDS`, and limited to four rounds.
Missing keys, invalid configuration, timeouts, malformed/unknown calls, tool failures,
and partial results are returned in structured envelopes without raw exceptions.

`FallbackAgent` provides deterministic routing for order/revenue, category/product,
seller, review, payment, and delivery questions. It extracts common years, first-half
ranges, the assignment's `last year` convention (2017), top-N limits, SP/São Paulo,
common metrics, and ascending/worst rankings. It records a full-dataset assumption when
no date range is present and returns `chart_hint.type = "bar"`; it does not generate
Chart.js configuration.

Agent tests can be run independently with:

```bash
pytest tests/test_agents.py
```

## Step 4 — Analytics Interpretation

The deterministic analytics layer consumes the Step 3 agent envelope through
`build_analytics_response()`. It does not execute SQL or call an LLM. The successful
response contains `question`, `chart` (`type`, `justification`, and JSON-serializable
Chart.js `config`), one-sentence `insight`, and result `metadata`.

Chart selection rules are explicit: time series use line charts, two time metrics use
dual-axis lines, ranked results use descending/ascending horizontal bars, category
comparisons use vertical bars, payment shares use doughnuts, two continuous variables
use scatter plots, and 1-5 review distributions use stacked horizontal bars with all
five buckets preserved. Genuine ambiguity can return up to two `chart_options`.

Empty results return `chart: null` with a clear no-data message. Unsupported questions
return `UNSUPPORTED_QUERY`; partial tool failures retain successful data and identify
failed tools in metadata. Insights are generated deterministically, use readable metric
formatting, and make no causal claims.

Run Step 4 tests with:

```bash
pytest tests/test_analytics.py
```

## Step 5 — Persistent Dashboard

Dashboard items are stored in the SQLite `dashboard_items` table. Each item retains the
original question, agent mode, structured allowlisted tool calls and arguments, chart
snapshot, complete analytics result snapshot, insight, and UTC creation/update timestamps.
The table is created automatically by the database schema and dashboard service; no
in-memory dictionary is used.

The backend routes are:

```text
POST /api/dashboard/pin
GET  /api/dashboard
POST /api/dashboard/{id}/refresh
```

Pinning accepts a successful Step 4 analysis with a non-null chart and rejects empty,
failed, unsupported, or non-predefined tool snapshots. Listing returns items ordered by
`updated_at DESC`, then `created_at DESC`.

Refresh replays the stored structured tool calls directly through the existing Step 2
allowlist, rebuilds the Step 4 chart and insight, compares the old and new snapshots, and
updates the row only after successful analysis. It never reinterprets the natural-language
question. Empty or failed refreshes preserve the previous valid dashboard item.

Change detection is deterministic: numeric aggregates and time-series totals use a 10%
relative-change threshold; payment shares use 5 percentage points; review scores use 0.3
points; delivery delay uses 1 day; ranking/order changes and at least 20% row-count changes
are significant. A first refresh without a comparable snapshot reports that no previous
snapshot is available.

## Basic Frontend

The frontend is intentionally small and functional. It provides one question input,
analysis results with a Chart.js chart, chart details, insight, pinning, and a dashboard
list with refresh/change messages. It uses the backend endpoints above plus
`POST /api/query`; local Vite requests are allowed from ports 5173.

With Node.js and npm installed:

```bash
cd frontend
npm install
npm run dev
```

The optional `VITE_API_URL` environment variable changes the backend base URL and defaults
to `http://localhost:8000`. No authentication, navigation, advanced filtering, or
production UI system is included.

Example questions:

- `monthly revenue trend in 2017`
- `revenue by category`
- `top 10 sellers by revenue in São Paulo`
- `review score distribution for electronics`
- `credit card vs boleto payment share`

## Step 2 — MCP Tool Layer

The official MCP 2.x Python SDK server in `app/mcp_server/server.py` exposes six
structured tools. The server opens no database connection at import or startup; each
domain query uses the existing connection context manager and closes its SQLite connection.
Start it over stdio with:

```bash
python -m app.mcp_server.server
```

Available tools and result grain:

- `order_trends(metric, from_date, to_date, granularity)`: one row per day, month, or year.
  Metrics are item revenue (`SUM(order_items.price)`), distinct order count, delivery delay
  in days (actual minus estimated), and on-time rate.
- `product_performance(metric, category, from_date, to_date, limit, sort)`: one row per
  translated English category for revenue, distinct order volume, average review score, or
  freight. Categories use the translation table and fall back to `[untranslated] <name>`.
- `seller_performance(metric, state, from_date, to_date, limit, sort)`: one row per seller,
  including seller ID, city, and state, for revenue, average review score, or delivery speed.
- `review_analysis(metric, category, seller_id, from_date, to_date, limit, sort)`: explicit
  score buckets 1 through 5, average score, category/seller score, or response time in hours.
- `payment_breakdown(metric, from_date, to_date)`: one row per payment type, or one row per
  month. `transaction_share` is transaction count share; `value_share` is payment-value share.
- `delivery_performance(metric, state, from_date, to_date, limit, sort)`: one row per customer
  state. Delay is actual delivery minus estimated delivery in days; missing actual dates are
  excluded, and on-time means actual delivery is on or before the estimate.

Dates are structured ISO `YYYY-MM-DD` values with inclusive bounds. Limits are restricted to
1 through 100 and sorting is restricted to `asc` or `desc`. Successful responses have
`success`, `data`, and `metadata`; expected invalid inputs return `INVALID_PARAMETER`, and
valid filters with no rows return `NO_RESULTS`. Unexpected query failures return a generic
`TOOL_FAILURE` without leaking a traceback.

All SQL is predefined and parameterized. Dynamic metrics, grouping, and sorting use explicit
allowlists; there is deliberately no arbitrary `execute_sql` MCP tool. This prevents the
future agent from turning natural-language input into unrestricted database access and avoids
join multiplication by aggregating only the relevant domain grain. Run MCP tests with:

```bash
pytest tests/test_mcp_tools.py
```

This step establishes the project skeleton only. The following are **implemented**:

- Full directory/module layout described above, with all Python packages importable.
- Minimal FastAPI app with a working `GET /health` endpoint.
- SQLite connection abstraction (`app/database/connection.py`) — reads `DATABASE_PATH`,
  does **not** load any data.
- MCP server skeleton (`app/mcp_server/server.py`) with no tools registered yet.
- `ILLMAgent` interface and `AgentResponse` contract, plus `LLMAgent`/`FallbackAgent`
  placeholder classes that raise `NotImplementedError`.
- Chart selection, insight generation, parameter handling, and refresh-comparison module
  stubs in `app/analytics/`.
- Dockerfile + docker-compose.yml that build and run the backend.
- `.env.example`, `.gitignore` (excludes `.env`), `pyproject.toml`, and a basic
  `pytest` test for `/health`.

The following are **explicitly not implemented yet** (by design, for this step):

- Analytics MCP tools (orders/products/sellers/reviews/payments/delivery) — currently
  empty modules.
- LLM tool-calling logic and rule-based fallback keyword matching.
- Olist CSV loading and SQLite schema design.
- `/query` endpoint and dashboard endpoints (pinning, refresh).
- Chart.js config generation and one-sentence insight generation.
- Frontend UI (only a placeholder directory exists).

**Step 1 will begin with:** inspecting the raw Olist CSVs and designing the SQLite schema.
