"""Review score and response-time analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates, validate_limit_sort

METRICS = {"distribution", "average", "category", "seller", "response_time"}


def review_analysis(metric: str = "distribution", category: str | None = None, seller_id: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 20, sort: str = "desc") -> dict[str, Any]:
	"""Return score buckets, averages, category/seller scores, or response time."""
	return execute_safe(_review_analysis, metric, category, seller_id, from_date, to_date, limit, sort)


def _review_analysis(metric: str, category: str | None, seller_id: str | None, from_date: str | None, to_date: str | None, limit: int, sort: str) -> dict[str, Any]:
	if metric not in METRICS:
		return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
	invalid = validate_dates(from_date, to_date) or validate_limit_sort(limit, sort)
	if invalid:
		return invalid
	date_sql, params = date_clause("r.review_creation_date", from_date, to_date)
	if metric == "distribution":
		data = rows(f"SELECT score, COUNT(r.review_score) AS value FROM (SELECT 1 AS score UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5) buckets LEFT JOIN order_reviews r ON r.review_score = score AND {date_sql} GROUP BY score ORDER BY score", params)
		if not any(row["value"] for row in data):
			return error("NO_RESULTS", "No data matched the supplied filters.")
		return success(data, metric, {"from_date": from_date, "to_date": to_date}, "one row per score 1-5")
	joins = ""
	where = date_sql
	if metric == "category":
		joins = "JOIN order_items i ON i.order_id = r.order_id JOIN products p ON p.product_id = i.product_id LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name"
		label = "COALESCE(t.product_category_name_english, '[untranslated] ' || p.product_category_name)"
		group = "category"
		value = "AVG(r.review_score)"
		if category:
			where += f" AND {label} = ?"
			params.append(category)
	elif metric == "seller":
		joins = "JOIN order_items i ON i.order_id = r.order_id JOIN sellers s ON s.seller_id = i.seller_id"
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
	order = "ASC" if sort == "asc" else "DESC"
	data = rows(f"SELECT {label} AS {group}, ROUND({value}, 2) AS value FROM order_reviews r {joins} WHERE {where} GROUP BY {group} ORDER BY value {order} LIMIT ?", [*params, limit])
	return success(data, metric, {"category": category, "seller_id": seller_id, "from_date": from_date, "to_date": to_date, "limit": limit, "sort": sort}, "one row per requested review group")
