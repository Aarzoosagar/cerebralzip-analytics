"""Delivery delay and on-time performance analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates, validate_limit_sort, validate_state


def delivery_performance(metric: str = "delay", state: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 20, sort: str = "desc") -> dict[str, Any]:
	"""Return delivery delay or on-time rate by Brazilian customer state."""
	return execute_safe(_delivery_performance, metric, state, from_date, to_date, limit, sort)


def _delivery_performance(metric: str, state: str | None, from_date: str | None, to_date: str | None, limit: int, sort: str) -> dict[str, Any]:
	if metric not in {"delay", "on_time_rate"}:
		return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
	invalid = validate_dates(from_date, to_date) or validate_limit_sort(limit, sort) or validate_state(state)
	if invalid:
		return invalid
	date_sql, params = date_clause("o.order_purchase_timestamp", from_date, to_date)
	state_sql = ""
	if state:
		state_sql = " AND c.customer_state = ?"
		params.append(state.upper())
	value = ("ROUND(AVG(julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date)), 2)"
			 if metric == "delay" else
			 "ROUND(100.0 * AVG(CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 1.0 ELSE 0.0 END), 2)")
	order = "ASC" if sort == "asc" else "DESC"
	data = rows(f"""SELECT c.customer_state AS state, {value} AS value, COUNT(*) AS order_count
		FROM orders o JOIN customers c ON c.customer_id = o.customer_id
		WHERE {date_sql} AND o.order_delivered_customer_date IS NOT NULL{state_sql}
		GROUP BY c.customer_state ORDER BY value {order} LIMIT ?""", [*params, limit])
	return success(data, metric, {"state": state, "from_date": from_date, "to_date": to_date, "limit": limit, "sort": sort}, "one row per customer state; missing delivery dates excluded")
