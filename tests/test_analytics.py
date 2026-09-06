"""Step 4 chart, response, and deterministic insight tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agent.fallback_agent import FallbackAgent
from app.analytics.chart_selector import select_chart_config
from app.analytics.insight import generate_insight
from app.analytics.response import build_analytics_response


pytestmark = pytest.mark.skipif(not Path("data/olist.db").exists(), reason="real Step 1 database is required")


def _rows(key: str = "period") -> list[dict]:
    return [{key: "Jan", "value": 10}, {key: "Feb", "value": 20}, {key: "Mar", "value": 15}]


def test_single_metric_over_time_is_line() -> None:
    chart = select_chart_config(_rows(), "monthly revenue in 2017", {"tool": "order_trends", "metric": "revenue"})
    assert chart["type"] == "line"
    assert chart["config"]["type"] == "line"
    assert chart["justification"]


def test_dual_axis_time_series() -> None:
    response = build_analytics_response("monthly orders and average review score in 2017", {
        "success": True, "results": [
            {"tool": "order_trends", "result": {"success": True, "data": [{"period": "2017-01", "value": 10}], "metadata": {"metric": "orders"}}},
            {"tool": "review_analysis", "result": {"success": True, "data": [{"period": "2017-01", "value": 4.2}], "metadata": {"metric": "review_score"}}},
        ], "tool_calls": [],
    })
    assert response["chart"]["type"] == "line"
    datasets = response["chart"]["config"]["data"]["datasets"]
    assert {dataset["yAxisID"] for dataset in datasets} == {"y", "y1"}


def test_ranked_horizontal_bar_is_sorted_descending() -> None:
    chart = select_chart_config([{"seller_id": "low", "value": 2}, {"seller_id": "high", "value": 9}], "top 10 sellers by revenue", {"tool": "seller_performance", "metric": "revenue", "ranking": True, "sort": "desc"})
    assert chart["type"] == "bar"
    assert chart["config"]["options"]["indexAxis"] == "y"
    assert chart["config"]["data"]["labels"] == ["high", "low"]


def test_category_vertical_bar() -> None:
    chart = select_chart_config([{"category": "A", "value": 4}, {"category": "B", "value": 8}], "revenue by category", {"tool": "product_performance", "metric": "revenue"})
    assert chart["type"] == "bar"
    assert "indexAxis" not in chart["config"]["options"]


def test_payment_share_is_doughnut() -> None:
    chart = select_chart_config([{"payment_type": "credit_card", "value": 70, "share": 70}, {"payment_type": "boleto", "value": 30, "share": 30}], "credit card vs boleto payment share", {"tool": "payment_breakdown", "metric": "value_share"})
    assert chart["type"] == "doughnut"
    assert chart["config"]["data"]["datasets"][0]["data"] == [70, 30]


def test_two_continuous_variables_are_scatter() -> None:
    chart = select_chart_config([{"entity": "SP", "x": 3.1, "y": 4.2}], "delivery delay vs review score by seller", {"scatter_data": True})
    assert chart["type"] == "scatter"
    assert chart["config"]["data"]["datasets"][0]["data"] == [{"x": 3.1, "y": 4.2}]


def test_review_distribution_preserves_zero_buckets() -> None:
    chart = select_chart_config([{"score": 1, "value": 2}, {"score": 3, "value": 4}, {"score": 5, "value": 1}], "review score distribution for electronics", {"tool": "review_analysis", "metric": "distribution"})
    assert chart["type"] == "bar"
    assert chart["config"]["options"]["indexAxis"] == "y"
    assert [dataset["data"] for dataset in chart["config"]["data"]["datasets"]] == [[2], [0], [4], [0], [1]]
    assert chart["config"]["options"]["scales"]["x"]["stacked"] is True


def test_ambiguous_query_can_return_two_options() -> None:
    chart = select_chart_config([{"category": "A", "value": 1}], "compare categories", {"ambiguous": True, "metric": "revenue"})
    assert len(chart["chart_options"]) == 2


def test_empty_and_unsupported_results_have_no_chart() -> None:
    empty = build_analytics_response("monthly revenue in 2030", {"success": False, "error": {"code": "NO_RESULTS", "message": "No data"}, "results": []})
    assert empty["success"] is True and empty["chart"] is None and empty["insight"] is None
    unsupported = build_analytics_response("What is the weather in São Paulo?", {"success": False, "error": {"code": "UNSUPPORTED_QUERY", "message": "Not analytics"}, "results": []})
    assert unsupported["success"] is False and unsupported["error"]["code"] == "UNSUPPORTED_QUERY"


def test_partial_results_are_preserved() -> None:
    response = build_analytics_response("revenue by category", {"success": True, "results": [
        {"tool": "product_performance", "result": {"success": True, "data": [{"category": "A", "value": 4}], "metadata": {"metric": "revenue"}}},
        {"tool": "review_analysis", "result": {"success": False, "error": {"code": "TOOL_FAILURE", "message": "failed"}}},
    ], "tool_calls": []})
    assert response["chart"] is not None
    assert response["metadata"]["partial_failures"] == ["review_analysis"]


def test_agent_to_analytics_integration_and_json_serialization() -> None:
    agent_result = asyncio.run(FallbackAgent().analyze("monthly revenue 2017"))
    response = build_analytics_response("monthly revenue 2017", agent_result)
    assert response["chart"]["type"] == "line"
    assert response["insight"].count(".") == 1
    json.dumps(response)


def test_insight_is_factual_and_not_causal() -> None:
    insight = generate_insight("revenue by category", [{"category": "Beauty", "value": 1200}], {"metric": "revenue"})
    assert insight == "Beauty had the highest revenue at R$1,200."
    assert "because" not in insight.lower()