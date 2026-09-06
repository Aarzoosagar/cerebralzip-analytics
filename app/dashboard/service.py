"""SQLite-backed dashboard pinning and refresh service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agent.tools import TOOL_FUNCTIONS, call_tool
from app.analytics.comparison import compare_results
from app.analytics.response import build_analytics_response
from app.database.connection import get_connection

CREATE_DASHBOARD_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_items (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    agent_mode TEXT,
    query_snapshot TEXT NOT NULL,
    chart_snapshot TEXT NOT NULL,
    result_snapshot TEXT NOT NULL,
    insight TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def initialize_dashboard_storage() -> None:
    with get_connection() as connection:
        connection.execute(CREATE_DASHBOARD_SQL)
        connection.commit()


def pin_chart(analysis: dict[str, Any]) -> dict[str, Any]:
    initialize_dashboard_storage()
    validation = _validate_analysis(analysis)
    if validation:
        return validation
    now = _now()
    item_id = str(uuid.uuid4())
    query_snapshot = {
        "question": analysis["question"],
        "agent_mode": analysis.get("agent_mode"),
        "tool_calls": analysis.get("tool_calls", []),
        "analysis": analysis.get("analysis", {}),
        "metadata": analysis.get("metadata", {}),
    }
    item = {
        "id": item_id,
        "question": analysis["question"],
        "agent_mode": analysis.get("agent_mode"),
        "query_snapshot": query_snapshot,
        "chart": analysis["chart"],
        "insight": analysis.get("insight"),
        "result_snapshot": analysis,
        "created_at": now,
        "updated_at": now,
    }
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO dashboard_items (id, question, agent_mode, query_snapshot, chart_snapshot, result_snapshot, insight, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, item["question"], item["agent_mode"], json.dumps(query_snapshot), json.dumps(item["chart"]), json.dumps(analysis), item["insight"], now, now),
        )
        connection.commit()
    return {"success": True, "id": item_id, "item": item}


def list_pinned_charts() -> dict[str, Any]:
    initialize_dashboard_storage()
    with get_connection() as connection:
        rows = connection.execute("SELECT id, question, agent_mode, query_snapshot, chart_snapshot, result_snapshot, insight, created_at, updated_at FROM dashboard_items ORDER BY updated_at DESC, created_at DESC").fetchall()
    return {"success": True, "items": [_row_to_item(row) for row in rows]}


def get_pinned_chart(item_id: str) -> dict[str, Any] | None:
    if not _valid_id(item_id):
        return None
    initialize_dashboard_storage()
    with get_connection() as connection:
        row = connection.execute("SELECT id, question, agent_mode, query_snapshot, chart_snapshot, result_snapshot, insight, created_at, updated_at FROM dashboard_items WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def delete_pinned_chart(item_id: str) -> dict[str, Any]:
    if not _valid_id(item_id):
        return _error("NOT_FOUND", "Pinned dashboard item was not found.")
    initialize_dashboard_storage()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM dashboard_items WHERE id = ?", (item_id,))
        connection.commit()
    if cursor.rowcount == 0:
        return _error("NOT_FOUND", "Pinned dashboard item was not found.")
    return {"success": True, "id": item_id}


async def refresh_pinned_chart(item_id: str) -> dict[str, Any]:
    item = get_pinned_chart(item_id)
    if item is None:
        return _error("NOT_FOUND", "Pinned dashboard item was not found.")
    calls = item["query_snapshot"].get("tool_calls", [])
    if not calls:
        return _error("INVALID_QUERY_SNAPSHOT", "The pinned item has no structured tool calls to replay.")
    results = []
    for call in calls:
        tool = call.get("tool")
        arguments = call.get("arguments")
        if tool not in TOOL_FUNCTIONS or not isinstance(arguments, dict):
            return _error("INVALID_QUERY_SNAPSHOT", "The pinned query contains an invalid predefined tool call.")
        results.append({"tool": tool, "result": await call_tool(tool, arguments)})
    failed = [entry for entry in results if not entry["result"].get("success")]
    if failed:
        if any((entry["result"].get("error") or {}).get("code") == "NO_RESULTS" for entry in failed):
            return _error("NO_RESULTS", "The refreshed query returned no data; the previous dashboard snapshot was preserved.", previous_item_preserved=True)
        return _error("REFRESH_FAILED", "The refreshed query failed; the previous dashboard snapshot was preserved.", previous_item_preserved=True)
    agent_response = {
        "success": True,
        "agent_mode": item.get("agent_mode"),
        "question": item["question"],
        "tool_calls": calls,
        "results": results,
        "analysis": item["query_snapshot"].get("analysis", {}),
    }
    refreshed = build_analytics_response(item["question"], agent_response)
    if not refreshed.get("success") or not refreshed.get("chart"):
        return _error("NO_RESULTS", "The refreshed query returned no data; the previous dashboard snapshot was preserved.", previous_item_preserved=True)
    change = compare_results(item["result_snapshot"], refreshed)
    now = _now()
    updated_item = {
        **item,
        "chart": refreshed["chart"],
        "insight": refreshed.get("insight"),
        "result_snapshot": refreshed,
        "updated_at": now,
    }
    with get_connection() as connection:
        connection.execute("UPDATE dashboard_items SET chart_snapshot = ?, result_snapshot = ?, insight = ?, updated_at = ? WHERE id = ?", (json.dumps(refreshed["chart"]), json.dumps(refreshed), refreshed.get("insight"), now, item_id))
        connection.commit()
    return {"success": True, "item": updated_item, "change": change}


def _validate_analysis(analysis: Any) -> dict[str, Any] | None:
    if not isinstance(analysis, dict) or not analysis.get("success"):
        return _error("INVALID_ANALYSIS", "Only successful analytics responses can be pinned.")
    if not analysis.get("chart"):
        return _error("INVALID_ANALYSIS", "A non-empty chart is required before pinning.")
    if not isinstance(analysis.get("question"), str) or not analysis["question"].strip():
        return _error("INVALID_ANALYSIS", "A question is required before pinning.")
    for call in analysis.get("tool_calls", []):
        if call.get("tool") not in TOOL_FUNCTIONS or not isinstance(call.get("arguments", {}), dict):
            return _error("INVALID_QUERY_SNAPSHOT", "Only predefined structured tool calls may be pinned.")
    return None


def _row_to_item(row: Any) -> dict[str, Any]:
    return {"id": row["id"], "question": row["question"], "agent_mode": row["agent_mode"], "query_snapshot": json.loads(row["query_snapshot"]), "chart": json.loads(row["chart_snapshot"]), "result_snapshot": json.loads(row["result_snapshot"]), "insight": row["insight"], "created_at": row["created_at"], "updated_at": row["updated_at"]}


def _valid_id(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}, **extra}
