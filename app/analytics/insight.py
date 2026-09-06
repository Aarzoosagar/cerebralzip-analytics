"""Deterministic, factual one-sentence insight generation."""

from __future__ import annotations

from typing import Any


def generate_insight(question: str, data: list[dict[str, Any]], metadata: dict[str, Any] | None = None) -> str | None:
    """Describe one observable fact without adding causal explanations."""
    if not data:
        return None
    context = metadata or {}
    metric = context.get("metric", "")
    text = question.lower()
    if "distribution" in text or metric == "distribution":
        row = max(data, key=lambda item: _number(item.get("value")))
        return f"The most common review score was {row.get('score')} with {_count(row.get('value'))} reviews."
    if "share" in text or metric in {"value_share", "transaction_share"}:
        row = max(data, key=lambda item: _number(item.get("share", item.get("value"))))
        return f"{_label(row)} represented the largest payment share at {_percent(row.get('share', row.get('value')))}."
    if any(word in text for word in ("top ", "best", "worst", "rank", "highest", "lowest")) or context.get("ranking"):
        row = data[0]
        noun = "seller" if "seller" in text else "category" if "categor" in text else "entity"
        return f"The leading {noun} was {_label(row)} with {_format_metric(row.get('value'), metric)}."
    if any("period" in row for row in data):
        row = max(data, key=lambda item: _number(item.get("value")))
        return f"The highest {_metric_name(metric)} occurred in {_display_label(row)} at {_format_metric(row.get('value'), metric)}."
    row = max(data, key=lambda item: _number(item.get("value")))
    return f"{_label(row)} had the highest {_metric_name(metric)} at {_format_metric(row.get('value'), metric)}."


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _label(row: dict[str, Any]) -> str:
    for key in ("category", "seller_id", "payment_type", "state", "period", "score", "entity", "label"):
        if key in row:
            return str(row[key])
    return "The selected result"


def _display_label(row: dict[str, Any]) -> str:
    label = _label(row)
    if len(label) == 7 and label[4] == "-" and label[:4].isdigit():
        import datetime
        return datetime.datetime.strptime(label, "%Y-%m").strftime("%B %Y")
    return label


def _count(value: Any) -> str:
    return f"{int(value):,}" if isinstance(value, (int, float)) else "the reported number of"


def _percent(value: Any) -> str:
    return f"{_number(value):.1f}%"


def _metric_name(metric: str) -> str:
    return {"revenue": "revenue", "orders": "orders", "review_score": "average review score", "freight": "freight", "delivery_delay": "delivery delay", "on_time_rate": "on-time rate"}.get(metric, metric.replace("_", " ") or "value")


def _format_metric(value: Any, metric: str) -> str:
    number = _number(value)
    if metric in {"revenue", "freight", "value_by_type"}:
        return f"R${number:,.0f}"
    if metric in {"on_time_rate", "value_share", "transaction_share"}:
        return f"{number:.1f}%"
    if metric == "orders":
        return f"{int(number):,} orders"
    if metric in {"delivery_delay", "delivery_speed"}:
        return f"{number:.1f} days"
    return f"{number:.2f}"
