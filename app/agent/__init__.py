"""Agent factory and public agent exports."""

from __future__ import annotations

from app.agent.config import agent_mode
from app.agent.fallback_agent import FallbackAgent
from app.agent.interface import ILLMAgent
from app.agent.llm_agent import LLMAgent


class AgentConfigurationError(ValueError):
	"""Raised when AGENT_MODE is not supported."""


def get_agent() -> ILLMAgent:
	mode = agent_mode()
	if mode == "llm":
		return LLMAgent()
	if mode == "fallback":
		return FallbackAgent()
	raise AgentConfigurationError(f"Unsupported AGENT_MODE: {mode}. Expected 'llm' or 'fallback'.")


__all__ = ["AgentConfigurationError", "FallbackAgent", "ILLMAgent", "LLMAgent", "get_agent"]
