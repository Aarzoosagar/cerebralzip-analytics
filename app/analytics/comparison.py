"""Deterministic comparison rules for dashboard refreshes."""

from __future__ import annotations

from typing import Any


def detect_significant_change(
    previous_data: list[dict[str, Any]],
    new_data: list[dict[str, Any]],
) -> bool:
    """Compatibility boolean using the default numeric comparison rules."""
    return compare_results(previous_data, new_data)["significant_change"]


def compare_results(previous: Any, new: Any) -> dict[str, Any]:
    """Compare chart/result snapshots using explicit domain thresholds.

    Numeric aggregates and time-series totals use a 10% relative threshold;
    payment shares use 5 percentage points, review scores 0.3 points, delivery
    delay 1 day, and ranking membership/order changes are significant.
    """
    old_data, old_metric = _extract(previous)
    new_data, new_metric = _extract(new)
    metric = new_metric or old_metric or ""
    if not old_data:
        return {"significant_change": False, "reasons": [], "summary": "No previous snapshot available for comparison."}
    if not new_data:
        return {"significant_change": True, "reasons": ["The refreshed result contains no data."], "summary": "Significant change detected."}
    reasons: list[str] = []
    old_values = [_number(row.get("value")) for row in old_data]
    new_values = [_number(row.get("value")) for row in new_data]
    if metric in {"value_share", "transaction_share"} or any("share" in row for row in new_data):
        for old, fresh in zip(old_values, new_values):
            if abs(fresh - old) >= 5:
                reasons.append(f"Payment share changed by {abs(fresh - old):.1f} percentage points.")
                break
    elif metric in {"review_score", "average", "category"} and "review" in metric:
        if abs(_average(new_values) - _average(old_values)) >= 0.3:
            reasons.append(f"Average review score changed by {abs(_average(new_values) - _average(old_values)):.2f} points.")
    elif metric in {"delivery_delay", "delay", "delivery_speed"}:
        if abs(_average(new_values) - _average(old_values)) >= 1:
            reasons.append(f"Delivery delay changed by {abs(_average(new_values) - _average(old_values)):.1f} days.")
    else:
        old_total, new_total = sum(old_values), sum(new_values)
        if _relative_change(old_total, new_total) >= 0.10:
            reasons.append(f"The aggregate metric changed by {_relative_change(old_total, new_total) * 100:.1f}%.")
    if len(old_data) and abs(len(new_data) - len(old_data)) / len(old_data) >= 0.20:
        reasons.append(f"The number of result rows changed from {len(old_data)} to {len(new_data)}.")
    old_labels = [_label(row) for row in old_data]
    new_labels = [_label(row) for row in new_data]
    if old_labels and new_labels and old_labels != new_labels and ("seller" in metric or "category" in metric or len(old_labels) > 1):
        reasons.append("The result ranking or entity order changed materially.")
    return {"significant_change": bool(reasons), "reasons": reasons, "summary": "Significant change detected." if reasons else "No significant change detected."}


def _extract(value: Any) -> tuple[list[dict[str, Any]], str]:
    if isinstance(value, list):
        return value, ""
    if not isinstance(value, dict):
        return [], ""
    metric = str((value.get("metadata") or {}).get("metric", ""))
    if isinstance(value.get("data"), list):
        return value["data"], metric
    chart_data = ((value.get("chart") or {}).get("config") or {}).get("data") or {}
    labels = chart_data.get("labels", [])
    datasets = chart_data.get("datasets", [])
    if not datasets:
        return [], metric
    values = datasets[0].get("data", [])
    return [{"label": label, "value": item} for label, item in zip(labels, values)], metric


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _relative_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0 if new == 0 else 1.0
    return abs(new - old) / abs(old)


def _label(row: dict[str, Any]) -> str:
    for key in ("label", "period", "category", "seller_id", "payment_type", "state", "score"):
        if key in row:
            return str(row[key])
    return ""
