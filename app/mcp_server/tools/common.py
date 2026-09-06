"""Shared validation and result helpers for the MCP analytics tools."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.database.connection import get_connection

MAX_LIMIT = 100
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def success(data: list[dict[str, Any]], metric: str, filters: dict[str, Any], grain: str) -> dict[str, Any]:
    if not data:
        return error("NO_RESULTS", "No data matched the supplied filters.")
    return {"success": True, "data": data, "metadata": {"row_count": len(data), "metric": metric, "filters": filters, "grain": grain}}


def error(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error": {"code": code, "message": message}}


def validate_dates(from_date: str | None, to_date: str | None) -> dict[str, Any] | None:
    for name, value in (("from_date", from_date), ("to_date", to_date)):
        if value is not None:
            try:
                if not DATE_RE.fullmatch(value):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                return error("INVALID_PARAMETER", f"{name} must be a valid YYYY-MM-DD date.")
    if from_date and to_date and from_date > to_date:
        return error("INVALID_PARAMETER", "from_date must be on or before to_date.")
    return None


def date_clause(column: str, from_date: str | None, to_date: str | None) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if from_date:
        clauses.append(f"{column} >= ?")
        params.append(f"{from_date}T00:00:00")
    if to_date:
        clauses.append(f"{column} < date(?, '+1 day')")
        params.append(to_date)
    return (" AND ".join(clauses) or "1 = 1", params)


def validate_limit_sort(limit: int, sort: str) -> dict[str, Any] | None:
    if limit < 1 or limit > MAX_LIMIT:
        return error("INVALID_PARAMETER", f"limit must be between 1 and {MAX_LIMIT}.")
    if sort not in {"asc", "desc"}:
        return error("INVALID_PARAMETER", "sort must be 'asc' or 'desc'.")
    return None


def validate_state(state: str | None) -> dict[str, Any] | None:
    if state is not None and (len(state) != 2 or not state.isalpha()):
        return error("INVALID_PARAMETER", "state must be a two-letter Brazilian state code.")
    return None


def rows(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def execute_safe(operation, *args, **kwargs) -> dict[str, Any]:
    try:
        return operation(*args, **kwargs)
    except Exception:
        return error("TOOL_FAILURE", "The analytics query could not be completed.")