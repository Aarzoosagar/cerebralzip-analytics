"""Focused Step 3 agent tests with deterministic tools and mocked Groq calls."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent import AgentConfigurationError, FallbackAgent, LLMAgent, get_agent
from app.agent.interface import ILLMAgent


pytestmark = pytest.mark.skipif(not Path("data/olist.db").exists(), reason="real Step 1 database is required")


def test_interface_requires_analyze() -> None:
    assert hasattr(ILLMAgent, "analyze")
    assert isinstance(FallbackAgent(), ILLMAgent)


def test_factory_modes_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "fallback")
    assert isinstance(get_agent(), FallbackAgent)
    monkeypatch.setenv("AGENT_MODE", "llm")
    assert isinstance(get_agent(), LLMAgent)
    monkeypatch.setenv("AGENT_MODE", "other")
    with pytest.raises(AgentConfigurationError):
        get_agent()


def test_fallback_parameters_and_no_date_assumption() -> None:
    result = asyncio.run(FallbackAgent().analyze("top 10 sellers by revenue in São Paulo"))
    call = result["tool_calls"][0]
    assert result["success"]
    assert call["tool"] == "seller_performance"
    assert call["arguments"]["state"] == "SP"
    assert call["arguments"]["limit"] == 10
    assert result["chart_hint"]["type"] == "bar"

    no_date = asyncio.run(FallbackAgent().analyze("revenue by category"))
    assert no_date["analysis"]["assumptions"]


def test_fallback_multi_tool_query() -> None:
    result = asyncio.run(FallbackAgent().analyze("Compare review scores across the top 2 categories by order volume"))
    assert result["success"]
    assert result["tool_calls"][0]["tool"] == "product_performance"
    assert len(result["tool_calls"]) > 1


def test_fallback_top_categories_uses_order_and_review_tools() -> None:
    question = "Which are the top 5 product categories by order volume, and how do their review scores compare?"
    result = asyncio.run(FallbackAgent().analyze(question))
    assert result["success"]
    assert result["tool_calls"][0]["tool"] == "product_performance"
    assert result["tool_calls"][0]["arguments"] == {"metric": "orders", "limit": 5, "sort": "desc", "category": None}
    assert [call["tool"] for call in result["tool_calls"][1:]] == ["review_analysis"] * 5
    assert len(result["results"][1]["result"]["data"]) == 1


def test_fallback_state_delay_comparison_uses_delivery_and_review_tools() -> None:
    result = asyncio.run(FallbackAgent().analyze("Which states have the longest delivery delays and how do their review scores compare?"))
    assert result["success"]
    assert result["tool_calls"][0]["tool"] == "delivery_performance"
    assert result["tool_calls"][0]["arguments"]["limit"] == 5
    assert [call["tool"] for call in result["tool_calls"][1:]] == ["review_analysis"]
    assert result["tool_calls"][1]["arguments"]["group_by_state"] is True


def test_fallback_worst_delivery_delays_sort_descending() -> None:
    result = asyncio.run(FallbackAgent().analyze("states with worst delivery delays"))
    assert result["success"]
    assert result["tool_calls"][0]["arguments"]["sort"] == "desc"
    values = [row["value"] for row in result["results"][0]["result"]["data"]]
    assert values == sorted(values, reverse=True)


def test_fallback_exact_faster_delivery_review_question_returns_scatter() -> None:
    from app.analytics.response import build_analytics_response

    question = "Do sellers with faster delivery get better reviews?"
    result = asyncio.run(FallbackAgent().analyze(question))
    assert [call["tool"] for call in result["tool_calls"]] == ["seller_performance", "seller_performance"]
    assert [call["arguments"]["metric"] for call in result["tool_calls"]] == ["delivery_speed", "review_score"]
    response = build_analytics_response(question, result)
    assert response["chart"]["type"] == "scatter"
    assert response["metadata"]["entity"] == "seller"
    assert response["metadata"]["x_metric"] == "delivery speed"
    assert response["metadata"]["y_metric"] == "average review score"
    assert response["chart"]["config"]["data"]["datasets"][0]["data"][0]["x"] is not None
    assert "relationship" in response["insight"].lower()


def test_fallback_faster_sellers_review_question_returns_seller_scatter() -> None:
    from app.analytics.response import build_analytics_response

    question = "Do faster sellers receive better reviews?"
    result = asyncio.run(FallbackAgent().analyze(question))
    assert [call["tool"] for call in result["tool_calls"]] == ["seller_performance", "seller_performance"]
    assert [call["arguments"]["metric"] for call in result["tool_calls"]] == ["delivery_speed", "review_score"]
    response = build_analytics_response(question, result)
    assert response["chart"]["type"] == "scatter"
    points = response["chart"]["config"]["data"]["datasets"][0]["data"]
    assert points and all(set(point) == {"x", "y"} for point in points)
    assert "state" not in response["insight"].lower()


def test_fallback_worst_delivery_performance_by_state_is_delivery_only() -> None:
    result = asyncio.run(FallbackAgent().analyze("Which states have the worst delivery performance?"))
    assert [call["tool"] for call in result["tool_calls"]] == ["delivery_performance"]


@pytest.mark.parametrize("question", [
    "Show delivery delay and review score side by side by state",
    "Show delivery delay and review score by state",
])
def test_fallback_state_delivery_review_cooccurrence_uses_both_tools(question: str) -> None:
    result = asyncio.run(FallbackAgent().analyze(question))
    assert [call["tool"] for call in result["tool_calls"]] == ["delivery_performance", "review_analysis"]


def test_fallback_state_delivery_review_query_uses_both_tools() -> None:
    result = asyncio.run(FallbackAgent().analyze("delivery delay + review score by state"))
    assert [call["tool"] for call in result["tool_calls"]] == ["delivery_performance", "review_analysis"]


@pytest.mark.parametrize("question", ["faster delivery vs better reviews", "How does faster delivery relate to better reviews?"])
def test_fallback_delivery_review_comparison_returns_seller_scatter(question: str) -> None:
    from app.analytics.response import build_analytics_response

    result = asyncio.run(FallbackAgent().analyze(question))
    assert result["success"]
    assert [call["tool"] for call in result["tool_calls"]] == ["seller_performance", "seller_performance"]
    assert [call["arguments"]["metric"] for call in result["tool_calls"]] == ["delivery_speed", "review_score"]
    response = build_analytics_response(question, result)
    points = response["chart"]["config"]["data"]["datasets"][0]["data"]
    assert response["chart"]["type"] == "scatter"
    assert len(points) > 1
    assert all(isinstance(point["x"], (int, float)) and isinstance(point["y"], (int, float)) for point in points)


def test_fallback_monthly_orders_and_reviews_uses_two_tools() -> None:
    result = asyncio.run(FallbackAgent().analyze("Show monthly orders and average review score together for 2017"))
    assert result["success"]
    assert [call["tool"] for call in result["tool_calls"]] == ["order_trends", "review_analysis"]
    assert result["tool_calls"][1]["arguments"]["granularity"] == "month"


class FakeCompletions:
    def __init__(self, responses: list[object], delay: float = 0) -> None:
        self.responses = iter(responses)
        self.calls: list[dict] = []
        self.delay = delay

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        return next(self.responses)


def _response(message: object) -> object:
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_llm_native_tool_call_and_final_response() -> None:
    tool_call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="order_trends", arguments='{"metric":"orders","from_date":"2017-01-01","to_date":"2017-12-31","granularity":"month"}'))
    fake = FakeCompletions([_response(SimpleNamespace(content=None, tool_calls=[tool_call])), _response(SimpleNamespace(content="Here is the monthly order trend.", tool_calls=[]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    result = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=client).analyze("monthly orders in 2017"))
    assert result["success"]
    assert result["tool_calls"][0]["arguments"]["metric"] == "orders"
    assert result["analysis"]["interpretation"] == "Here is the monthly order trend."
    assert len(fake.calls) == 2
    assert fake.calls[0]["tools"]


def test_llm_multiple_tools_and_partial_failure() -> None:
    calls = [
        SimpleNamespace(id="a", function=SimpleNamespace(name="order_trends", arguments='{"metric":"orders"}')),
        SimpleNamespace(id="b", function=SimpleNamespace(name="unknown_tool", arguments='{}')),
    ]
    fake = FakeCompletions([_response(SimpleNamespace(content=None, tool_calls=calls)), _response(SimpleNamespace(content="Partial results available.", tool_calls=[]))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    result = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=client).analyze("orders and another source"))
    assert result["success"]
    assert len(result["results"]) == 2
    assert result["results"][1]["result"]["error"]["code"] == "UNKNOWN_TOOL"


def test_llm_missing_key_timeout_and_malformed_call() -> None:
    missing = asyncio.run(LLMAgent(api_key=None, model="fake-model", client=None).analyze("orders"))
    assert missing["success"] and missing["fallback_used"] is True
    assert missing["fallback_reason"] == "MISSING_GROQ_API_KEY"

    slow = FakeCompletions([], delay=0.05)
    client = SimpleNamespace(chat=SimpleNamespace(completions=slow))
    timeout = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=client, timeout_seconds=0.001).analyze("orders"))
    assert timeout["success"] and timeout["fallback_used"] is True
    assert timeout["fallback_reason"] == "LLM_TIMEOUT"

    malformed_call = SimpleNamespace(id="bad", function=SimpleNamespace(name="order_trends", arguments="not-json"))
    malformed = FakeCompletions([_response(SimpleNamespace(content=None, tool_calls=[malformed_call]))])
    malformed_client = SimpleNamespace(chat=SimpleNamespace(completions=malformed))
    result = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=malformed_client).analyze("orders"))
    assert result["error"]["code"] == "MALFORMED_TOOL_CALL"
    assert result["results"][0]["result"]["error"]["code"] == "MALFORMED_TOOL_CALL"


def test_llm_api_failure_uses_fallback() -> None:
    class FailingCompletions:
        def create(self, **kwargs):
            raise ConnectionError("network unavailable")

    client = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletions()))
    result = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=client).analyze("monthly orders in 2017"))
    assert result["success"]
    assert result["agent_mode"] == "fallback"
    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "LLM_API_FAILURE"


def test_fallback_mode_does_not_call_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_MODE", "fallback")
    agent = get_agent()
    assert isinstance(agent, FallbackAgent)
    result = asyncio.run(agent.analyze("monthly orders in 2017"))
    assert result["agent_mode"] == "fallback"
