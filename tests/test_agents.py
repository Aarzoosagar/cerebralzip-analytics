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
    assert missing["error"]["code"] == "MISSING_GROQ_API_KEY"

    slow = FakeCompletions([], delay=0.05)
    client = SimpleNamespace(chat=SimpleNamespace(completions=slow))
    timeout = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=client, timeout_seconds=0.001).analyze("orders"))
    assert timeout["error"]["code"] == "LLM_TIMEOUT"

    malformed_call = SimpleNamespace(id="bad", function=SimpleNamespace(name="order_trends", arguments="not-json"))
    malformed = FakeCompletions([_response(SimpleNamespace(content=None, tool_calls=[malformed_call]))])
    malformed_client = SimpleNamespace(chat=SimpleNamespace(completions=malformed))
    result = asyncio.run(LLMAgent(api_key="test", model="fake-model", client=malformed_client).analyze("orders"))
    assert result["error"]["code"] == "MALFORMED_TOOL_CALL"
    assert result["results"][0]["result"]["error"]["code"] == "MALFORMED_TOOL_CALL"