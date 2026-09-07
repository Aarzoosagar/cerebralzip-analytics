"""Seller performance analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates, validate_limit_sort, validate_state

METRICS = {"revenue", "review_score", "delivery_speed"}


def seller_performance(metric: str = "revenue", state: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 20, sort: str = "desc") -> dict[str, Any]:
	"""Return one row per seller with revenue, reviews, or delivery speed."""
	return execute_safe(_seller_performance, metric, state, from_date, to_date, limit, sort)


def _seller_performance(metric: str, state: str | None, from_date: str | None, to_date: str | None, limit: int, sort: str) -> dict[str, Any]:
	if metric not in METRICS:
		return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
	invalid = validate_dates(from_date, to_date) or validate_limit_sort(limit, sort) or validate_state(state)
	if invalid:
		return invalid
	date_sql, params = date_clause("o.order_purchase_timestamp", from_date, to_date)
	state_sql = ""
	if state:
		state_sql = " AND s.seller_state = ?"
		params.append(state.upper())
	expressions = {
		"revenue": "ROUND(SUM(i.price), 2)",
		"review_score": "ROUND(AVG(r.review_score), 2)",
		"delivery_speed": "ROUND(AVG(julianday(o.order_delivered_customer_date) - julianday(o.order_purchase_timestamp)), 2)",
	}
	order = "ASC" if sort == "asc" else "DESC"
	# A seller can have multiple items in one order.  Deduplicate seller/order
	# pairs before joining reviews so a single order review is counted once.
	from_sql = "order_items i JOIN orders o ON o.order_id = i.order_id"
	if metric == "review_score":
		from_sql = "(SELECT DISTINCT seller_id, order_id FROM order_items) i JOIN orders o ON o.order_id = i.order_id"
	review_join = "LEFT JOIN order_reviews r ON r.order_id = i.order_id" if metric == "review_score" else ""
	delivery_filter = " AND o.order_delivered_customer_date IS NOT NULL" if metric == "delivery_speed" else ""
	data = rows(f"""SELECT s.seller_id, s.seller_city, s.seller_state, {expressions[metric]} AS value
		FROM {from_sql}
		JOIN sellers s ON s.seller_id = i.seller_id
		{review_join}
		WHERE {date_sql}{delivery_filter}{state_sql}
		GROUP BY s.seller_id, s.seller_city, s.seller_state ORDER BY value {order} LIMIT ?""", [*params, limit])
	return success(data, metric, {"state": state, "from_date": from_date, "to_date": to_date, "limit": limit, "sort": sort}, "one row per seller")
