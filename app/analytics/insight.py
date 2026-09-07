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
    if context.get("scatter_data"):
        return _scatter_insight(data)
    if "distribution" in text or metric == "distribution":
        row = max(data, key=lambda item: _number(item.get("value")))
        return f"The most common review score was {row.get('score')} with {_count(row.get('value'))} reviews."
    if "share" in text or metric in {"value_share", "transaction_share"}:
        row = max(data, key=lambda item: _number(item.get("share", item.get("value"))))
        return f"{_label(row)} represented the largest payment share at {_percent(row.get('share', row.get('value')))}."
    if ("delivery" in text or "delay" in text) and metric in {"delay", "delivery_delay"} and any(word in text for word in ("worst", "longest")) and "review" not in text:
        row = data[0]
        scope = "among the selected states" if "state" in row else "among the selected entities"
        return f"{_label(row)} had the longest delivery delay {scope} at {_format_metric(row.get('value'), metric)}."
    if context.get("state_series") and context.get("state_labels"):
        return f"The state with the longest average delivery delay was {context['state_labels'][0]} at {_format_metric(data[0].get('value'), 'delivery_delay')}, with an average review score of {_format_metric(context['state_series'][1]['values'][0], 'review_score')}."
    if any(word in text for word in ("top ", "best", "worst", "rank", "highest", "lowest")) or context.get("ranking"):
        if context.get("category_series") and context.get("category_labels"):
            labels = context["category_labels"]
            scores = context["category_series"][1]["values"]
            return f"{labels[0]} had the highest order volume at {_format_metric(data[0].get('value'), 'orders')} and an average review score of {_format_metric(scores[0], 'review_score')}."
        row = data[0]
        if ("delivery" in text or "delay" in text) and metric in {"delay", "delivery_delay"} and any(word in text for word in ("worst", "longest")):
            scope = "among the selected states" if "state" in row else "among the selected entities"
            return f"{_label(row)} had the longest delivery delay {scope} at {_format_metric(row.get('value'), metric)}."
        noun = "seller" if "seller" in text else "category" if "categor" in text else "entity"
        return f"The leading {noun} was {_label(row)} with {_format_metric(row.get('value'), metric)}."
    if any("period" in row for row in data):
        row = max(data, key=lambda item: _number(item.get("value")))
        return f"The highest {_metric_name(metric)} occurred in {_display_label(row)} at {_format_metric(row.get('value'), metric)}."
    row = max(data, key=lambda item: _number(item.get("value")))
    return f"{_label(row)} had the highest {_metric_name(metric)} at {_format_metric(row.get('value'), metric)}."


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _scatter_insight(data: list[dict[str, Any]]) -> str:
    pairs = [(float(row["x"]), float(row["y"])) for row in data if isinstance(row.get("x"), (int, float)) and isinstance(row.get("y"), (int, float))]
    if len(pairs) < 3:
        return "Across sellers, the data shows no clear relationship between faster delivery and higher review scores."
    xs, ys = zip(*pairs)
    x_centered = [value - sum(xs) / len(xs) for value in xs]
    y_centered = [value - sum(ys) / len(ys) for value in ys]
    denominator = (sum(value * value for value in x_centered) * sum(value * value for value in y_centered)) ** 0.5
    if not denominator:
        return "Across sellers, the data shows no clear relationship between faster delivery and higher review scores."
    relationship = sum(x * y for x, y in zip(x_centered, y_centered)) / denominator
    if relationship <= -0.5:
        return "Across sellers, the data shows a clear positive relationship: faster delivery times tend to coincide with higher review scores."
    if relationship >= 0.5:
        return "Across sellers, the data shows a clear negative relationship: longer delivery times tend to coincide with higher review scores."
    return "Across sellers, the data shows no clear relationship between faster delivery and higher review scores."


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
    if metric in {"delay", "delivery_delay", "delivery_speed"}:
        return f"{number:.2f} days"
    return f"{number:.2f}"
