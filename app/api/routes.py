"""Core health and analytics query routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.agent import get_agent
from app.analytics.response import build_analytics_response
from app.schemas.responses import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Simple liveness check used to verify the backend started correctly."""
    return HealthResponse(status="ok")


@router.post("/api/query")
async def query(payload: dict[str, Any]) -> dict:
    raw_question = payload.get("question", "")
    question = raw_question.strip() if isinstance(raw_question, str) else ""
    if not question:
        return {"success": False, "question": question, "chart": None, "error": {"code": "INVALID_PARAMETER", "message": "question is required."}}
    try:
        agent_response = await get_agent().analyze(question)
        return build_analytics_response(question, agent_response)
    except Exception:
        return {"success": False, "question": question, "chart": None, "error": {"code": "QUERY_FAILURE", "message": "The analytics query could not be completed."}}
