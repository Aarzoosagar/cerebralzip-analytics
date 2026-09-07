"""Review score and response-time analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates, validate_limit_sort, validate_state

METRICS = {"distribution", "average", "category", "seller", "response_time"}
GRANULARITIES = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}


def review_analysis(metric: str = "distribution", category: str | None = None, seller_id: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 20, sort: str = "desc", granularity: str | None = None, state: str | None = None, group_by_state: bool = False) -> dict[str, Any]:
	"""Return score buckets, averages, category/seller scores, or response time."""
	return execute_safe(_review_analysis, metric, category, seller_id, from_date, to_date, limit, sort, granularity, state, group_by_state)


def _review_analysis(metric: str, category: str | None, seller_id: str | None, from_date: str | None, to_date: str | None, limit: int, sort: str, granularity: str | None, state: str | None, group_by_state: bool) -> dict[str, Any]:
	if metric not in METRICS:
		return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
	if granularity is not None and granularity not in GRANULARITIES:
		return error("INVALID_PARAMETER", f"Unsupported granularity: {granularity}")
	invalid = validate_dates(from_date, to_date) or validate_limit_sort(limit, sort) or validate_state(state)
	if invalid:
		return invalid
	date_sql, params = date_clause("r.review_creation_date", from_date, to_date)
	if metric == "distribution":
		category_filter = ""
		if category:
			# EXISTS filters reviews by orders containing the translated category
			# without multiplying a review when its order has several items.
			category_filter = """ AND EXISTS (
				SELECT 1 FROM order_items i JOIN products p ON p.product_id = i.product_id
				LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
				WHERE i.order_id = r.order_id
				AND COALESCE(t.product_category_name_english, '[untranslated] ' || p.product_category_name) = ?
			)"""
			params.append(category)
		data = rows(f"SELECT score, COUNT(r.review_score) AS value FROM (SELECT 1 AS score UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5) buckets LEFT JOIN order_reviews r ON r.review_score = score AND {date_sql}{category_filter} GROUP BY score ORDER BY score", params)
		if not any(row["value"] for row in data):
			return error("NO_RESULTS", "No data matched the supplied filters.")
		return success(data, metric, {"category": category, "from_date": from_date, "to_date": to_date}, "one row per score 1-5")
	joins = ""
	where = date_sql
	state_join = ""
	if state or group_by_state:
		state_join = " JOIN orders o ON o.order_id = r.order_id JOIN customers c ON c.customer_id = o.customer_id"
	if state:
		where += " AND c.customer_state = ?"
		params.append(state.upper())
	if metric == "category":
		joins = "JOIN (SELECT DISTINCT i.order_id, COALESCE(t.product_category_name_english, '[untranslated] ' || p.product_category_name) AS category FROM order_items i JOIN products p ON p.product_id = i.product_id LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name) categories ON categories.order_id = r.order_id"
		label = "categories.category"
		group = "category"
		value = "AVG(r.review_score)"
		if category:
			where += f" AND {label} = ?"
			params.append(category)
	elif metric == "seller":
		joins = "JOIN (SELECT DISTINCT order_id, seller_id FROM order_items) i ON i.order_id = r.order_id JOIN sellers s ON s.seller_id = i.seller_id"
		label = "s.seller_id"
		group = "seller_id"
		value = "AVG(r.review_score)"
		if seller_id:
			where += " AND s.seller_id = ?"
			params.append(seller_id)
	elif metric == "response_time":
		label = "r.review_id"
		group = "review_id"
		value = "AVG((julianday(r.review_answer_timestamp) - julianday(r.review_creation_date)) * 24.0)"
		where += " AND r.review_answer_timestamp IS NOT NULL"
	else:
		label = "'average'"
		group = "label"
		value = "AVG(r.review_score)"
		if granularity:
			label = f"strftime('{GRANULARITIES[granularity]}', r.review_creation_date)"
			group = "period"
		if state:
			label = "c.customer_state"
			group = "state"
		if group_by_state:
			label = "c.customer_state"
			group = "state"
	group_by = "s.seller_id" if metric == "seller" else group
	order = "ASC" if sort == "asc" else "DESC"
	order_by = f"{group} ASC" if granularity else f"value {order}"
	data = rows(f"SELECT {label} AS {group}, ROUND({value}, 2) AS value FROM order_reviews r{state_join} {joins} WHERE {where} GROUP BY {group_by} ORDER BY {order_by} LIMIT ?", [*params, limit])
	return success(data, "review_score" if granularity or state or group_by_state else metric, {"category": category, "seller_id": seller_id, "state": state, "group_by_state": group_by_state, "from_date": from_date, "to_date": to_date, "limit": limit, "sort": sort, "granularity": granularity}, "one row per requested review group")
