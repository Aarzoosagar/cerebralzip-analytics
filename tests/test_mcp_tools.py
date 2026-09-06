"""Direct integration checks for the six Step 2 MCP domain tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.mcp_server.server import create_server
from app.mcp_server.tools.delivery import delivery_performance
from app.mcp_server.tools.orders import order_trends
from app.mcp_server.tools.payments import payment_breakdown
from app.mcp_server.tools.products import product_performance
from app.mcp_server.tools.reviews import review_analysis
from app.mcp_server.tools.sellers import seller_performance


pytestmark = pytest.mark.skipif(not Path("data/olist.db").exists(), reason="real Step 1 database is required")


def test_order_trends_revenue_and_orders() -> None:
    revenue = order_trends(metric="revenue", from_date="2017-01-01", to_date="2017-12-31")
    orders = order_trends(metric="orders", from_date="2017-01-01", to_date="2017-12-31")
    assert revenue["success"] and len(revenue["data"]) == 12
    assert orders["success"] and all("period" in row and "value" in row for row in orders["data"])


def test_invalid_and_empty_order_inputs_are_structured() -> None:
    assert order_trends(metric="bad")["error"]["code"] == "INVALID_PARAMETER"
    assert order_trends(metric="orders", from_date="2030-01-01", to_date="2030-01-02")["error"]["code"] == "NO_RESULTS"


def test_product_category_uses_english_translation() -> None:
    result = product_performance(metric="revenue", limit=5)
    assert result["success"]
    assert all("category" in row for row in result["data"])
    assert any(row["category"] != "[untranslated] " for row in result["data"])
    assert any(row["category"] == "health_beauty" for row in result["data"])
    assert all(row["category"] != "beleza_saude" for row in result["data"])
    assert product_performance(metric="bad")["error"]["code"] == "INVALID_PARAMETER"


def test_seller_state_limit_and_sort() -> None:
    result = seller_performance(metric="revenue", state="SP", limit=3, sort="desc")
    assert result["success"] and len(result["data"]) == 3
    assert all(row["seller_state"] == "SP" for row in result["data"])
    assert result["data"][0]["value"] >= result["data"][1]["value"]


def test_reviews_include_all_score_buckets() -> None:
    result = review_analysis(metric="distribution")
    assert result["success"]
    assert [row["score"] for row in result["data"]] == [1, 2, 3, 4, 5]
    assert review_analysis(metric="response_time")["success"]
    assert review_analysis(metric="distribution", from_date="2030-01-01", to_date="2030-01-02")["error"]["code"] == "NO_RESULTS"


def test_payments_expose_value_share_and_date_filter() -> None:
    result = payment_breakdown(metric="value_share", from_date="2017-01-01", to_date="2017-12-31")
    assert result["success"]
    assert all("payment_type" in row and "share" in row for row in result["data"])
    assert payment_breakdown(metric="bad")["error"]["code"] == "INVALID_PARAMETER"


def test_delivery_excludes_missing_actual_dates() -> None:
    result = delivery_performance(metric="delay", limit=5)
    assert result["success"]
    assert all("state" in row and "value" in row for row in result["data"])
    assert delivery_performance(metric="on_time_rate", from_date="2030-01-01", to_date="2030-01-02")["error"]["code"] == "NO_RESULTS"
    assert delivery_performance(state="invalid")["error"]["code"] == "INVALID_PARAMETER"


def test_mcp_server_exposes_all_tools() -> None:
    import asyncio

    async def names() -> list[str]:
        return [tool.name for tool in await create_server().list_tools()]

    assert (names_result := asyncio.run(names()))
    assert set(names_result) == {"order_trends", "product_performance", "seller_performance", "review_analysis", "payment_breakdown", "delivery_performance"}


def test_mcp_dispatcher_executes_structured_tool_call() -> None:
    import asyncio

    async def call():
        return await create_server().call_tool("order_trends", {"metric": "orders", "from_date": "2017-01-01", "to_date": "2017-01-31", "granularity": "month"})

    result = asyncio.run(call())
    assert result.is_error is False
    assert result.structured_content["success"] is True