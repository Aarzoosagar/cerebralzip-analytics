# CerebralZip Analytics

CerebralZip is an e-commerce analytics chatbot for the Olist Brazilian E-Commerce Public Dataset. It accepts plain-English questions, uses controlled MCP tools for data access, and returns deterministic chart configurations and factual one-sentence insights.

## Architecture

```text
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

`LLMAgent` and `FallbackAgent` implement the interchangeable `ILLMAgent` interface. The LLM agent uses Groq native tool calling. Recoverable LLM failures automatically invoke the deterministic fallback agent; `AGENT_MODE=fallback` uses only the fallback agent.

## Stack

- Python 3.11, FastAPI, and SQLite
- Olist dataset loaded through pandas and the existing database loader
- Official Python MCP SDK with order, product, seller, review, payment, and delivery tools
- Groq native tool-calling agent and deterministic rule-based fallback
- Deterministic chart selection and one-sentence insight generation
- React, Vite, and Chart.js frontend
- Persistent SQLite dashboard storage
- Docker Compose and pytest

## Fresh Clone Setup

The recommended setup requires only a Groq API key for LLM access:

```bash
git clone <repository-url>
cd cerebralzip-analytics
copy .env.example .env
```

Set `GROQ_API_KEY` in `.env`, then start the complete application:

```bash
docker compose up --build
```

The backend starts on `http://localhost:8000` and the frontend on `http://localhost:5173`. On first backend startup, the application downloads the public Olist archive, extracts the CSV files, and initializes SQLite before serving requests. Existing initialized databases are reused.

## Environment Variables

`.env` is git-ignored. Values shown here are the defaults used by the application or Docker Compose.

| Variable | Default | Description |
| --- | --- | --- |
| `AGENT_MODE` | `llm` in `.env.example`, `fallback` in Compose when unset | Preferred agent: `llm` or `fallback`. |
| `GROQ_API_KEY` | Empty | The only required manual value for LLM access. Leave empty to use automatic LLM-to-fallback recovery or explicit fallback mode. |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Groq model used for native tool calling. Manual configuration is optional. |
| `LLM_TIMEOUT_SECONDS` | `20` | LLM request timeout before automatic fallback. |
| `DATABASE_PATH` | `data/olist.db` locally, `/app/data/olist.db` in Compose | SQLite database path. |
| `DATA_DIR` | Database parent directory | Runtime directory for CSV files and downloaded data. |
| `DATASET_URL` | Version-pinned public Olist archive | Optional URL override for the dataset ZIP. |
| `API_HOST` | `0.0.0.0` in Compose | FastAPI bind host. |
| `API_PORT` | `8000` in Compose | FastAPI bind port. |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed frontend origin. |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend URL used by the frontend. |

### Agent Modes

With `AGENT_MODE=llm`, the system uses Groq native function calling and dispatches selected operations through the MCP tools. Timeouts, missing LLM configuration, recoverable Groq/API failures, network failures, and exhausted tool-call rounds automatically run the fallback agent and preserve `fallback_used` and `fallback_reason` metadata.

With `AGENT_MODE=fallback`, the deterministic rule-based agent is used directly and the LLM is not called. This mode is useful for deterministic demonstrations or environments without LLM access.

## Dataset Bootstrap

The source is the official [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/olistbr/brazilian-ecommerce). The default version-pinned archive URL is:

```text
https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce?datasetVersionNumber=2
```

This is a public archive and does not require Kaggle CLI authentication, browser login, cookies, API tokens, or credentials. It contains the nine expected files:

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

When required, `app/database/bootstrap.py` downloads and safely extracts the archive into `DATA_DIR`, then calls the existing `load_olist_dataset()` implementation. Initialization is idempotent: missing, empty, incomplete, or invalid databases are loaded; initialized databases with populated orders are reused. CSV files, ZIP archives, and SQLite databases are runtime artifacts ignored by Git.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Backend liveness check. |
| `POST` | `/api/query` | Analyze a question and return chart, insight, and metadata. |
| `GET` | `/api/dashboard` | List persisted dashboard items. |
| `POST` | `/api/dashboard/pin` | Persist a successful chart analysis. |
| `POST` | `/api/dashboard/{item_id}/refresh` | Replay stored tool calls and refresh an item. |
| `DELETE` | `/api/dashboard/{item_id}` | Remove a persisted dashboard item. |

Dashboard records retain the question, agent mode, structured tool calls, chart snapshot, analytics result, insight, and timestamps in SQLite. Refresh compares new and previous snapshots and preserves the prior item when refresh data is empty or fails.

## MCP Tools

The official MCP 2.x Python SDK server exposes six structured tools: `order_trends`, `product_performance`, `seller_performance`, `review_analysis`, `payment_breakdown`, and `delivery_performance`. All SQL is predefined, parameterized, and constrained by allowlisted metrics, grouping, dates, limits, and sorting. The LLM never executes arbitrary SQL.

The tools provide time-based order and payment metrics, translated product categories, seller metrics, review distributions and averages, payment shares, and delivery delay/on-time metrics. Delivery delay is actual delivery minus estimated delivery; orders without actual delivery timestamps are excluded. Review and category/state relationships use the existing order relationships without join multiplication.

## Chart Selection

- Time series -> line chart
- Two metrics over time -> dual-axis line chart
- Ranked top-N results -> horizontal bar chart
- General category comparison -> vertical bar chart
- Order-volume/category review comparison -> two-dataset bar chart with separate axes
- Delivery-delay/state review comparison -> horizontal two-dataset bar chart with separate axes
- Part-to-whole shares -> doughnut chart
- Two continuous variables -> scatter chart
- Review-score distribution -> stacked horizontal bar chart with score buckets 1 through 5

## Validated Questions

- `Show monthly orders and average review score together for 2017`
- `Which are the top 5 product categories by order volume, and how do their review scores compare?`
- `Which states have the longest delivery delays and how do their review scores compare?`
- `Show monthly revenue in 2017`
- `Show revenue by category`
- `Show payment share`
- `Show the top sellers in Sao Paulo by revenue`

## Frontend

The React/Vite frontend sends questions to `/api/query`, renders the returned Chart.js configuration and insight, and supports dashboard listing, pinning, refresh, and removal. Its API base defaults to `http://localhost:8000` and can be changed with `VITE_API_BASE_URL`.

## Testing

Run the complete suite with:

```bash
python -m pytest -q
```

Verified result: **62 passed, 0 failed, with one dependency deprecation warning**.

## Docker

`docker compose up --build` starts the backend and frontend services. The backend performs automatic database initialization before serving requests and exposes the readiness check at `http://localhost:8000/health`.

## Local Development

For local Python development, install the project and run the same FastAPI application. Startup bootstrap still handles the database automatically:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env
uvicorn app.main:app --reload
```
