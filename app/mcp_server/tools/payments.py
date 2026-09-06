"""Payment type and value analytics."""

from __future__ import annotations

from typing import Any

from .common import date_clause, error, execute_safe, rows, success, validate_dates


def payment_breakdown(metric: str = "value_by_type", from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
	"""Return payment value, transaction counts, installment, or value share by type."""
	return execute_safe(_payment_breakdown, metric, from_date, to_date)


def _payment_breakdown(metric: str, from_date: str | None, to_date: str | None) -> dict[str, Any]:
	allowed = {"value_by_type", "transaction_share", "value_share", "installments", "value_by_period"}
	if metric not in allowed:
		return error("INVALID_PARAMETER", f"Unsupported metric: {metric}")
	invalid = validate_dates(from_date, to_date)
	if invalid:
		return invalid
	date_sql, params = date_clause("o.order_purchase_timestamp", from_date, to_date)
	if metric == "value_by_period":
		select, group, grain = "strftime('%Y-%m', o.order_purchase_timestamp) AS period, ROUND(SUM(p.payment_value), 2) AS value", "period", "one row per payment month"
	elif metric == "installments":
		select, group, grain = "p.payment_type, ROUND(AVG(p.payment_installments), 2) AS value", "p.payment_type", "one row per payment type"
	elif metric == "transaction_share":
		select, group, grain = "p.payment_type, COUNT(*) AS value, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share", "p.payment_type", "one row per payment type; share is transaction share"
	elif metric == "value_share":
		select, group, grain = "p.payment_type, ROUND(SUM(p.payment_value), 2) AS value, ROUND(100.0 * SUM(p.payment_value) / SUM(SUM(p.payment_value)) OVER (), 2) AS share", "p.payment_type", "one row per payment type; share is payment-value share"
	else:
		select, group, grain = "p.payment_type, ROUND(SUM(p.payment_value), 2) AS value", "p.payment_type", "one row per payment type"
	data = rows(f"SELECT {select} FROM order_payments p JOIN orders o ON o.order_id = p.order_id WHERE {date_sql} GROUP BY {group} ORDER BY value DESC", params)
	return success(data, metric, {"from_date": from_date, "to_date": to_date}, grain)
