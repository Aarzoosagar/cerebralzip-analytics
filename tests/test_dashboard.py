"""Step 5 persistence, refresh, comparison, and API tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analytics.comparison import compare_results
from app.dashboard import service
from app.main import app


@pytest.fixture
def dashboard_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "dashboard.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    service.initialize_dashboard_storage()
    return path


def _analysis(value: float = 100) -> dict:
    return {
        "success": True,
        "agent_mode": "fallback",
        "question": "monthly revenue 2017",
        "tool_calls": [{"tool": "order_trends", "arguments": {"metric": "revenue", "from_date": "2017-01-01", "to_date": "2017-12-31", "granularity": "month"}}],
        "results": [],
        "chart": {"type": "line", "justification": "Time series", "config": {"type": "line", "data": {"labels": ["2017-01"], "datasets": [{"label": "Revenue", "data": [value]}]}, "options": {}}},
        "insight": "Revenue was reported.",
        "metadata": {"metric": "revenue", "row_count": 1},
    }


def test_pin_list_and_persistence_after_reopen(dashboard_db: Path) -> None:
    pinned = service.pin_chart(_analysis())
    assert pinned["success"]
    item_id = pinned["id"]
    listed = service.list_pinned_charts()
    assert listed["items"][0]["id"] == item_id
    assert listed["items"][0]["query_snapshot"]["tool_calls"][0]["arguments"]["from_date"] == "2017-01-01"
    service.initialize_dashboard_storage()
    assert service.get_pinned_chart(item_id)["question"] == "monthly revenue 2017"


def test_delete_pinned_chart_removes_existing_item(dashboard_db: Path) -> None:
    pinned = service.pin_chart(_analysis())
    assert service.delete_pinned_chart(pinned["id"])["success"]
    assert service.get_pinned_chart(pinned["id"]) is None
    assert service.list_pinned_charts()["items"] == []


def test_delete_pinned_chart_returns_structured_not_found(dashboard_db: Path) -> None:
    assert service.delete_pinned_chart("not-a-uuid")["error"]["code"] == "NOT_FOUND"
    missing_id = "00000000-0000-0000-0000-000000000000"
    assert service.delete_pinned_chart(missing_id)["error"]["code"] == "NOT_FOUND"


def test_cannot_pin_failed_or_empty_analysis(dashboard_db: Path) -> None:
    assert service.pin_chart({"success": False})["error"]["code"] == "INVALID_ANALYSIS"
    assert service.pin_chart({"success": True, "question": "empty", "chart": None})["error"]["code"] == "INVALID_ANALYSIS"
    assert service.pin_chart({"success": False, "error": {"code": "UNSUPPORTED_QUERY"}})["error"]["code"] == "INVALID_ANALYSIS"


def test_comparison_thresholds_and_first_snapshot() -> None:
    assert compare_results([], [{"value": 115}])["summary"] == "No previous snapshot available for comparison."
    assert compare_results([{"value": 100}], [{"value": 115}])["significant_change"] is True
    assert compare_results([{"value": 100}], [{"value": 105}])["significant_change"] is False
    assert compare_results({"metadata": {"metric": "value_share"}, "chart": {"config": {"data": {"labels": ["a"], "datasets": [{"data": [50]}]}}}}, {"metadata": {"metric": "value_share"}, "chart": {"config": {"data": {"labels": ["a"], "datasets": [{"data": [54]}]}}}})["significant_change"] is False
    assert compare_results({"metadata": {"metric": "value_share"}, "chart": {"config": {"data": {"labels": ["a"], "datasets": [{"data": [50]}]}}}}, {"metadata": {"metric": "value_share"}, "chart": {"config": {"data": {"labels": ["a"], "datasets": [{"data": [56]}]}}}})["significant_change"] is True
    assert compare_results([{"value": 4.0}], [{"value": 4.2}])["significant_change"] is False
    assert compare_results([{"value": 4.0}], [{"value": 4.4}])["significant_change"] is True
    assert compare_results([{"label": "a", "value": 1}, {"label": "b", "value": 2}], [{"label": "b", "value": 2}, {"label": "a", "value": 1}])["significant_change"] is True


def test_refresh_replays_stored_arguments_and_updates(monkeypatch: pytest.MonkeyPatch, dashboard_db: Path) -> None:
    item_id = service.pin_chart(_analysis())["id"]
    calls = []

    async def fake_call(tool: str, arguments: dict) -> dict:
        calls.append((tool, arguments))
        return {"success": True, "data": [{"period": "2017-01", "value": 115}], "metadata": {"metric": "revenue", "row_count": 1}}

    monkeypatch.setattr(service, "call_tool", fake_call)
    refreshed = asyncio.run(service.refresh_pinned_chart(item_id))
    assert refreshed["success"]
    assert calls[0][1] == _analysis()["tool_calls"][0]["arguments"]
    assert refreshed["change"]["significant_change"] is True
    assert refreshed["item"]["result_snapshot"]["chart"]["type"] == "line"


def test_empty_refresh_preserves_previous_item(monkeypatch: pytest.MonkeyPatch, dashboard_db: Path) -> None:
    original = service.pin_chart(_analysis())

    async def empty_call(tool: str, arguments: dict) -> dict:
        return {"success": False, "error": {"code": "NO_RESULTS", "message": "none"}}

    monkeypatch.setattr(service, "call_tool", empty_call)
    refreshed = asyncio.run(service.refresh_pinned_chart(original["id"]))
    assert refreshed["success"] is False
    assert refreshed["previous_item_preserved"] is True
    assert service.get_pinned_chart(original["id"])["chart"] == original["item"]["chart"]


def test_refresh_tool_failure_preserves_previous_item(monkeypatch: pytest.MonkeyPatch, dashboard_db: Path) -> None:
    original = service.pin_chart(_analysis())

    async def failing_call(tool: str, arguments: dict) -> dict:
        return {"success": False, "error": {"code": "TOOL_FAILURE", "message": "failed"}}

    monkeypatch.setattr(service, "call_tool", failing_call)
    refreshed = asyncio.run(service.refresh_pinned_chart(original["id"]))
    assert refreshed["error"]["code"] == "REFRESH_FAILED"
    assert service.get_pinned_chart(original["id"])["updated_at"] == original["item"]["updated_at"]


def test_dashboard_api_routes(dashboard_db: Path) -> None:
    with TestClient(app) as client:
        pinned = client.post("/api/dashboard/pin", json={"analysis": _analysis()})
        assert pinned.status_code == 200 and pinned.json()["success"]
        listed = client.get("/api/dashboard")
        assert listed.status_code == 200 and len(listed.json()["items"]) == 1
        missing = client.post("/api/dashboard/not-a-uuid/refresh")
        assert missing.status_code == 200 and missing.json()["error"]["code"] == "NOT_FOUND"
        removed = client.delete(f"/api/dashboard/{pinned.json()['id']}")
        assert removed.status_code == 200 and removed.json()["success"]
        assert client.get("/api/dashboard").json()["items"] == []
        missing_delete = client.delete("/api/dashboard/not-a-uuid")
        assert missing_delete.status_code == 200 and missing_delete.json()["error"]["code"] == "NOT_FOUND"
