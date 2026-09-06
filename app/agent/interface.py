"""Interchangeable agent contract for Step 3."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ILLMAgent(ABC):
    """Abstraction over "something that turns a question into an answer".

    Implementations decide how to interpret the question and which MCP
    tools to call. They must never execute arbitrary SQL directly — all
    data access goes through controlled MCP tools.
    """

    @abstractmethod
    async def analyze(self, question: str) -> dict[str, Any]:
        """Interpret a question, call controlled tools, and return the common envelope."""
        raise NotImplementedError

    async def answer_query(self, question: str) -> dict[str, Any]:
        """Compatibility alias for the Step 0 method name."""
        return await self.analyze(question)
