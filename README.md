# CerebralZip Analytics

CerebralZip is an e-commerce analytics chatbot for the Olist Brazilian E-Commerce Public
Dataset. It accepts plain-English questions, uses controlled MCP tools for data access, and
returns deterministic chart configurations and factual one-sentence insights that can be
pinned to a persistent, refreshable dashboard.

## Architecture

```
User question
    |
Agent (LLMAgent or FallbackAgent)
    |
MCP server and six allowlisted analytics tools
    |
Deterministic analytics and chart selection
    |
Insight plus Chart.js configuration
    |
React/Vite frontend and persistent dashboard
```

`LLMAgent` and `FallbackAgent` implement the interchangeable `ILLMAgent` interface. The LLM
agent uses Groq native tool calling. Recoverable LLM failures (timeout, missing key, API
error, exhausted tool-call rounds) automatically invoke the deterministic fallback agent.
`AGENT_MODE=fallback` uses only the fallback agent and never calls Groq.

## Stack

- Python 3.11, FastAPI, and SQLite
- Olist dataset loaded through pandas and the database loader (`app/database/loader.py`)
- Official Python MCP SDK with order, product, seller, review, payment, and delivery tools
- Groq native tool-calling agent and a deterministic rule-based fallback
- Deterministic chart selection and one-sentence insight generation
- React, Vite, and Chart.js frontend
- Persistent SQLite dashboard storage
- Docker Compose and pytest

## Fresh Clone Setup (one command)

```bash
git clone <repository-url>
cd cerebralzip-analytics
cp .env.example .env
```

Add your `GROQ_API_KEY` to `.env` if you want LLM mode. Then start everything:

```bash
docker compose up --build
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

On first backend startup, the app downloads the public Olist archive, extracts the CSVs,
and initializes SQLite before serving requests. Existing initialized databases are reused,
so subsequent `docker compose up` runs are fast. No manual step is required beyond the
optional API key.

## Environment Variables

`.env` is git-ignored. Values below are the defaults used by the application or Docker
Compose.

| Variable | Default | Description |
|---|---|---|
| `AGENT_MODE` | `llm` in `.env.example`, `fallback` in Compose when unset | Preferred agent: `llm` or `fallback`. |
| `GROQ_API_KEY` | Empty | Only required for LLM mode. Leave empty for automatic fallback or explicit `AGENT_MODE=fallback`. |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Groq model used for native tool calling. |
| `LLM_TIMEOUT_SECONDS` | `20` | LLM request timeout before automatic fallback. |
| `DATABASE_PATH` | `data/olist.db` locally, `/app/data/olist.db` in Compose | SQLite database path. |
| `DATA_DIR` | Database parent directory | Runtime directory for CSV files and downloaded data. |
| `DATASET_URL` | Version-pinned public Olist archive | Optional override for the dataset ZIP URL. |
| `API_HOST` | `0.0.0.0` in Compose | FastAPI bind host. |
| `API_PORT` | `8000` in Compose | FastAPI bind port. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed frontend origin. |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend URL used by the frontend. |

## Agent Modes

With `AGENT_MODE=llm`, the system uses Groq native function calling and dispatches selected
operations through the MCP tools. Timeouts, missing LLM configuration, recoverable
Groq/API failures, network failures, and exhausted tool-call rounds automatically run the
fallback agent and preserve `fallback_used` and `fallback_reason` metadata in the response.

With `AGENT_MODE=fallback`, the deterministic rule-based agent is used directly and the LLM
is never called. This mode is fully deterministic and is the recommended mode for grading
or any environment without reliable LLM access.

## Dataset Bootstrap

Source: the official Brazilian E-Commerce Public Dataset by Olist. Default archive URL:

```
https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce?datasetVersionNumber=2
```

This is a public archive and does not require Kaggle CLI authentication, browser login,
cookies, API tokens, or credentials. It contains the nine expected files:

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

`app/database/bootstrap.py` downloads and safely extracts the archive into `DATA_DIR`, then
calls `load_olist_dataset()`. Initialization is idempotent: missing, empty, incomplete, or
invalid databases are (re)loaded; an initialized database with populated orders is reused.
CSVs, ZIP archives, and the SQLite database are runtime artifacts ignored by Git.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Backend liveness check. |
| `POST` | `/api/query` | Analyze a question and return chart, insight, and metadata. |
| `GET` | `/api/dashboard` | List persisted dashboard items. |
| `POST` | `/api/dashboard/pin` | Persist a successful chart analysis. |
| `POST` | `/api/dashboard/{item_id}/refresh` | Replay stored tool calls and refresh an item. |
| `DELETE` | `/api/dashboard/{item_id}` | Remove a persisted dashboard item. |

Dashboard records retain the question, agent mode, structured tool calls, chart snapshot,
analytics result, insight, and timestamps in SQLite. Refresh compares the new snapshot
against the previous one and preserves the prior item if the refresh returns empty data or
fails outright.

## MCP Tools

The official MCP 2.x Python SDK server exposes six structured tools: `order_trends`,
`product_performance`, `seller_performance`, `review_analysis`, `payment_breakdown`, and
`delivery_performance`. All SQL is predefined, parameterized, and constrained by allowlisted
metrics, grouping, dates, limits, and sorting — the LLM never executes arbitrary SQL.

Product and category results are always joined against `product_category_name_translation`
before being returned. Delivery delay is actual delivery timestamp minus estimated delivery
date; orders without an actual delivery timestamp are excluded. Seller review scores are
deduplicated at the order/seller level so multi-item orders don't inflate review counts.

## Chart Selection

| Data shape | Chart type |
|---|---|
| Single metric over time | Line chart |
| Two metrics over the same time axis | Dual-axis line chart |
| Ranked top-N results | Horizontal bar chart, sorted descending |
| Category comparison in a single period | Vertical bar chart |
| Order-volume/category + review comparison | Two-dataset bar chart, separate axes |
| Delivery-delay/state + review comparison | Horizontal two-dataset bar chart, separate axes |
| Part-to-whole (e.g. payment type share) | Doughnut chart |
| Two continuous variables per entity | Scatter chart |
| Review-score distribution (1–5) | Stacked horizontal bar chart |

The chart type and a one-line justification are always included in the `/api/query`
response. If the data shape is genuinely ambiguous, two chart options are returned instead
of one.

## Demo Walkthrough

Run these five queries in order to exercise the core single-tool paths:

1. `Show monthly revenue trend in 2017` — time-series line chart.
2. `Which product categories generate the most revenue?` — ranked horizontal bar with
   translated category names.
3. `Which states have the worst delivery performance?` — ranked delivery-delay bar chart.
4. `What share of payments are credit card vs boleto?` — payment-share doughnut chart.
5. `Top 10 sellers by revenue in São Paulo` — filtered, ranked seller bar chart.

Additional multi-tool examples:

- `Compare review scores across the top 5 categories by order volume`
- `Show monthly orders and average review score together for 2017`
- `Do sellers with faster delivery get better reviews?`
- `Show delivery delay and review score side by side by state`

## Design Decisions

**Chart type selection.** Chart type is chosen from data shape, not randomly: one metric
over time gets a line chart, two time-aligned metrics get a dual-axis line, ranked lists get
a sorted horizontal bar, single-period category comparisons get a vertical bar, part-to-whole
breakdowns get a doughnut, two continuous variables per entity get a scatter plot, and 1–5
review distributions get a stacked horizontal bar. Every response includes the chart type
plus a one-line justification; genuinely ambiguous shapes return two chart options instead
of guessing.

**Refresh and significant-change detection.** Pinning a chart stores its exact structured
tool calls, not just its rendered output. Refreshing an item replays those calls against the
current database and diffs the new result against the stored snapshot using
metric-specific thresholds: roughly 10% relative change for most aggregate metrics, 5
percentage points for share-of-total metrics (like payment mix), 0.3 points for average
review score, and 1 day for delivery delay. If a refresh returns no data or fails outright,
the previous snapshot is preserved rather than overwritten, so a transient failure can't
silently blank out a pinned chart.

**What the fallback agent does differently.** `FallbackAgent` never calls an LLM. It uses
deterministic keyword and phrase matching to select the required MCP tools and extract
supported parameters. The final chart type is determined by the same deterministic
chart-selection logic used by the LLM path, so supported queries can correctly produce
line, bar, doughnut, stacked-bar, or scatter visualizations. This makes fallback mode
reproducible and useful when LLM access is unavailable or unreliable.

## Known Limitations

- LLM-based tool selection can be affected by model behavior and may occasionally require a
  retry if the model selects an unintended tool. The deterministic fallback mode is
  available for reproducible execution.
- Natural-language date interpretation is explicitly guided by the system prompt and
  fallback rules, but LLM output can still be non-deterministic. If a date range appears
  incorrect, the query can be rerun or fallback mode can be used for deterministic
  behavior.

## Frontend

The React/Vite frontend sends questions to `/api/query`, renders the returned Chart.js
configuration and insight, and supports dashboard listing, pinning, refresh, and removal.
Its API base defaults to `http://localhost:8000` and can be changed with
`VITE_API_BASE_URL`.

## Testing

Run the complete suite with:

```bash
python -m pytest -q
```

> **Before submitting:** re-run this locally against your own environment (with the real
> Olist dataset loaded) and replace this line with the actual current result — the count
> shifts depending on whether `data/olist.db` is already populated, since a real database
> unlocks additional integration tests that are otherwise skipped.

## Docker

`docker compose up --build` starts the backend and frontend services. The backend performs
automatic database initialization before serving requests and exposes a readiness check at
`http://localhost:8000/health`.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```
