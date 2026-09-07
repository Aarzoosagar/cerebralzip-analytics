"""Product and translated category performance analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates, validate_limit_sort

METRICS = {"revenue", "orders", "review_score", "freight"}


def product_performance(metric: str = "revenue", category: str | None = None, from_date: str | None = None, to_date: str | None = None, limit: int = 20, sort: str = "desc") -> dict[str, Any]:
    """Return one row per English product category, optionally filtered and ranked."""
    return execute_safe(_product_performance, metric, category, from_date, to_date, limit, sort)


def _product_performance(metric: str, category: str | None, from_date: str | None, to_date: str | None, limit: int, sort: str) -> dict[str, Any]:
    if metric not in METRICS:
        return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
    invalid = validate_dates(from_date, to_date) or validate_limit_sort(limit, sort)
    if invalid:
        return invalid
    date_sql, params = date_clause("o.order_purchase_timestamp", from_date, to_date)
    category_sql = ""
    if category:
        category_sql = " AND COALESCE(t.product_category_name_english, p.product_category_name) = ?"
        params.append(category)
    order = "ASC" if sort == "asc" else "DESC"
    if metric == "review_score":
        data = rows(f"""SELECT categories.category, ROUND(AVG(r.review_score), 2) AS value
            FROM (SELECT DISTINCT i.order_id, COALESCE(t.product_category_name_english, '[untranslated] ' || p.product_category_name) AS category
                FROM order_items i JOIN products p ON p.product_id = i.product_id
                LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name) categories
            JOIN orders o ON o.order_id = categories.order_id
            LEFT JOIN order_reviews r ON r.order_id = categories.order_id
            WHERE {date_sql}{" AND categories.category = ?" if category else ""}
            GROUP BY categories.category ORDER BY value {order} LIMIT ?""", [*params, limit])
        return success(data, metric, {"category": category, "from_date": from_date, "to_date": to_date, "limit": limit, "sort": sort}, "one row per translated category")
    expressions = {
        "revenue": "ROUND(SUM(i.price), 2)", "orders": "COUNT(DISTINCT i.order_id)",
        "freight": "ROUND(SUM(i.freight_value), 2)",
    }
    value = expressions[metric]
    data = rows(f"""SELECT COALESCE(t.product_category_name_english, '[untranslated] ' || p.product_category_name) AS category,
        {value} AS value
        FROM order_items i JOIN orders o ON o.order_id = i.order_id
        JOIN products p ON p.product_id = i.product_id
        LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
        WHERE {date_sql}{category_sql}
        GROUP BY category ORDER BY value {order} LIMIT ?""", [*params, limit])
    return success(data, metric, {"category": category, "from_date": from_date, "to_date": to_date, "limit": limit, "sort": sort}, "one row per translated category")
