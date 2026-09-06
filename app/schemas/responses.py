"""Pydantic response models for the FastAPI layer.

Step 0 scope: minimal HealthResponse only. Response models for /query and
the dashboard endpoints are added alongside those features in later steps.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
