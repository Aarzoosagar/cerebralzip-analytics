"""Order trend analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates

METRICS = {"revenue", "orders", "delivery_delay", "on_time_rate"}
GRANULARITIES = {"day": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}


def order_trends(metric: str = "revenue", from_date: str | None = None, to_date: str | None = None, granularity: str = "month") -> dict[str, Any]:
    """Return one row per time period for item revenue, orders, or delivery metrics."""
    return execute_safe(_order_trends, metric, from_date, to_date, granularity)


def _order_trends(metric: str, from_date: str | None, to_date: str | None, granularity: str) -> dict[str, Any]:
    if metric not in METRICS:
        return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
    if granularity not in GRANULARITIES:
        return error("INVALID_PARAMETER", f"Unsupported granularity: {granularity}")
    invalid = validate_dates(from_date, to_date)
    if invalid:
        return invalid
    period = f"strftime('{GRANULARITIES[granularity]}', o.order_purchase_timestamp)"
    date_sql, params = date_clause("o.order_purchase_timestamp", from_date, to_date)
    if metric == "revenue":
        value = "ROUND(SUM(i.price), 2) AS value"
        join = "JOIN order_items i ON i.order_id = o.order_id"
    elif metric == "orders":
        value = "COUNT(DISTINCT o.order_id) AS value"
        join = ""
    else:
        value = ("ROUND(AVG(julianday(o.order_delivered_customer_date) - julianday(o.order_estimated_delivery_date)), 2) AS value"
                 if metric == "delivery_delay" else
                 "ROUND(100.0 * AVG(CASE WHEN o.order_delivered_customer_date <= o.order_estimated_delivery_date THEN 1.0 ELSE 0.0 END), 2) AS value")
        join = ""
        date_sql += " AND o.order_delivered_customer_date IS NOT NULL"
    data = rows(f"SELECT {period} AS period, {value} FROM orders o {join} WHERE {date_sql} GROUP BY period ORDER BY period", params)
    return success(data, metric, {"from_date": from_date, "to_date": to_date, "granularity": granularity}, "one row per period")
