"""Persistent dashboard pin, list, and refresh endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.dashboard.service import delete_pinned_chart, list_pinned_charts, pin_chart, refresh_pinned_chart

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.post("/pin")
async def pin_dashboard_chart(payload: dict[str, Any]) -> dict[str, Any]:
	return pin_chart(payload.get("analysis", payload))


@router.get("")
async def get_dashboard() -> dict[str, Any]:
	return list_pinned_charts()


@router.post("/{item_id}/refresh")
async def refresh_dashboard_chart(item_id: str) -> dict[str, Any]:
	return await refresh_pinned_chart(item_id)


@router.delete("/{item_id}")
async def delete_dashboard_chart(item_id: str) -> dict[str, Any]:
	return delete_pinned_chart(item_id)
