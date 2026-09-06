"""Environment-backed configuration for the agent layer."""

from __future__ import annotations

import os


def agent_mode() -> str:
    return os.environ.get("AGENT_MODE", "fallback").strip().lower()


def groq_api_key() -> str | None:
    return os.environ.get("GROQ_API_KEY") or None


def llm_model() -> str | None:
    return os.environ.get("LLM_MODEL") or None


def llm_timeout_seconds() -> float:
    try:
        return max(0.1, float(os.environ.get("LLM_TIMEOUT_SECONDS", "20")))
    except ValueError:
        return 20.0