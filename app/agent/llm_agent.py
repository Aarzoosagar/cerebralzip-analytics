"""Groq-backed native tool-calling agent."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from groq import Groq

from app.agent.config import groq_api_key, llm_model, llm_timeout_seconds
from app.agent.interface import ILLMAgent
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import TOOL_DEFINITIONS, call_tool

MAX_TOOL_ROUNDS = 4


class LLMAgent(ILLMAgent):
    """Uses Groq function calling and only the six allowlisted analytics tools."""

    def __init__(self, api_key: str | None = None, model: str | None = None, client: Any | None = None, timeout_seconds: float | None = None) -> None:
        self.api_key = api_key if api_key is not None else groq_api_key()
        self.model = model if model is not None else llm_model()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else llm_timeout_seconds()
        self.client = client or (Groq(api_key=self.api_key) if self.api_key else None)

    async def analyze(self, question: str) -> dict[str, Any]:
        base: dict[str, Any] = {"success": False, "agent_mode": "llm", "question": question, "tool_calls": [], "results": []}
        if not question.strip():
            return {**base, "error": {"code": "INVALID_PARAMETER", "message": "question must not be empty."}}
        if not self.api_key or self.client is None:
            return {**base, "error": {"code": "MISSING_GROQ_API_KEY", "message": "GROQ_API_KEY is required when AGENT_MODE=llm."}}
        if not self.model:
            return {**base, "error": {"code": "INVALID_MODEL_CONFIGURATION", "message": "LLM_MODEL must be configured when AGENT_MODE=llm."}}
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
        assumptions = _assumptions(question)
        final_text = ""
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = await self._completion(messages)
            except asyncio.TimeoutError:
                return self._error_response(base, "LLM_TIMEOUT", "The language model request timed out.", assumptions)
            except Exception:
                return self._error_response(base, "LLM_API_FAILURE", "The language model request failed.", assumptions)
            message = response.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            final_text = getattr(message, "content", None) or final_text
            if not tool_calls:
                base["success"] = True
                base["analysis"] = {"interpretation": final_text or "Analytics results returned.", "assumptions": assumptions, "suggested_analysis": _suggested_analysis(question)}
                return base
            assistant_calls = []
            tool_messages = []
            malformed_call = False
            for tool_call in tool_calls:
                function_call = _attribute(tool_call, "function", {})
                name = _attribute(function_call, "name")
                raw_arguments = _attribute(function_call, "arguments", "{}")
                call_id = _attribute(tool_call, "id", "")
                try:
                    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be a JSON object")
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    result = {"success": False, "error": {"code": "MALFORMED_TOOL_CALL", "message": str(exc)}}
                    arguments = {}
                    malformed_call = True
                else:
                    result = await call_tool(name, arguments)
                base["tool_calls"].append({"tool": name, "arguments": arguments})
                base["results"].append({"tool": name, "result": result})
                assistant_calls.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}})
                tool_messages.append({"role": "tool", "tool_call_id": call_id, "content": json.dumps(result)})
            messages.append({"role": "assistant", "content": getattr(message, "content", None), "tool_calls": assistant_calls})
            messages.extend(tool_messages)
            if malformed_call:
                return self._error_response(base, "MALFORMED_TOOL_CALL", "The language model returned malformed tool arguments.", assumptions)
        return self._error_response(base, "TOOL_CALL_LIMIT", "The language model exceeded the maximum tool-call rounds.", assumptions)

    async def _completion(self, messages: list[dict[str, Any]]) -> Any:
        request = await asyncio.wait_for(asyncio.to_thread(self.client.chat.completions.create, messages=messages, model=self.model, tools=TOOL_DEFINITIONS, tool_choice="auto"), timeout=self.timeout_seconds)
        return await request if inspect.isawaitable(request) else request

    @staticmethod
    def _error_response(base: dict[str, Any], code: str, message: str, assumptions: list[str]) -> dict[str, Any]:
        base["error"] = {"code": code, "message": message}
        base["analysis"] = {"interpretation": "", "assumptions": assumptions, "suggested_analysis": {}}
        return base


def _attribute(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _assumptions(question: str) -> list[str]:
    if not any(token in question.lower() for token in ("20", "date", "year", "month", "quarter", "half")):
        return ["No date range was specified, so the full available dataset was used."]
    return []


def _suggested_analysis(question: str) -> dict[str, bool]:
    text = question.lower()
    return {"time_based": any(word in text for word in ("monthly", "daily", "trend", "year")), "ranking": any(word in text for word in ("top", "worst", "best")), "category_comparison": "categor" in text, "part_to_whole": "share" in text, "distribution": "distribution" in text}
