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


def test_top_five_categories_by_order_volume_are_translated_and_descending() -> None:
    result = product_performance(metric="orders", limit=5, sort="desc")
    assert result["success"]
    assert len(result["data"]) == 5
    assert [row["value"] for row in result["data"]] == sorted((row["value"] for row in result["data"]), reverse=True)
    assert all(row["category"] != "beleza_saude" for row in result["data"])


def test_category_review_scores_match_top_five_categories() -> None:
    categories = product_performance(metric="orders", limit=5, sort="desc")["data"]
    scores = [review_analysis(metric="category", category=row["category"], limit=1, sort="desc") for row in categories]
    assert all(result["success"] and result["data"][0]["category"] == category["category"] for result, category in zip(scores, categories))
    assert all(isinstance(result["data"][0]["value"], (int, float)) for result in scores)


def test_reviews_include_all_score_buckets() -> None:
    result = review_analysis(metric="distribution")
    assert result["success"]
    assert [row["score"] for row in result["data"]] == [1, 2, 3, 4, 5]
    assert review_analysis(metric="response_time")["success"]
    assert review_analysis(metric="distribution", from_date="2030-01-01", to_date="2030-01-02")["error"]["code"] == "NO_RESULTS"


def test_category_review_distribution_is_filtered_without_join_multiplication() -> None:
    global_distribution = review_analysis(metric="distribution")
    electronics = review_analysis(metric="distribution", category="electronics")
    assert electronics["success"]
    assert [row["score"] for row in electronics["data"]] == [1, 2, 3, 4, 5]
    assert electronics["data"] != global_distribution["data"]
    # Compare against EXISTS-based order filtering: every review is counted once.
    from app.mcp_server.tools.common import rows

    expected = rows("""SELECT r.review_score AS score, COUNT(*) AS value FROM order_reviews r
        WHERE EXISTS (SELECT 1 FROM order_items i JOIN products p ON p.product_id = i.product_id
        LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
        WHERE i.order_id = r.order_id AND t.product_category_name_english = ?) GROUP BY r.review_score ORDER BY score""", ["electronics"])
    expected_buckets = {row["score"]: row["value"] for row in expected}
    assert {row["score"]: row["value"] for row in electronics["data"]} == {score: expected_buckets.get(score, 0) for score in range(1, 6)}


def test_monthly_average_review_score_returns_2017_periods() -> None:
    result = review_analysis(metric="average", granularity="month", from_date="2017-01-01", to_date="2017-12-31", limit=100, sort="asc")
    assert result["success"]
    assert [row["period"] for row in result["data"]] == [f"2017-{month:02d}" for month in range(1, 13)]
    assert all(isinstance(row["value"], (int, float)) for row in result["data"])


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


def test_delivery_delay_states_are_ranked_without_duplicate_rows() -> None:
    result = delivery_performance(metric="delay", limit=5, sort="desc")
    assert result["success"]
    assert len(result["data"]) == 5
    assert [row["value"] for row in result["data"]] == sorted((row["value"] for row in result["data"]), reverse=True)
    assert len({row["state"] for row in result["data"]}) == 5


def test_review_analysis_returns_one_average_score_per_state() -> None:
    result = review_analysis(metric="average", state="SP", limit=1)
    assert result["success"]
    assert result["data"][0]["state"] == "SP"
    assert isinstance(result["data"][0]["value"], (int, float))


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
