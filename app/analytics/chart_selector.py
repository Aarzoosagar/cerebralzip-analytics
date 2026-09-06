"""Deterministic chart selection and Chart.js configuration generation."""

from __future__ import annotations

from typing import Any


def select_chart_config(
    data: list[dict[str, Any]],
    question: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a chart descriptor containing type, justification, and config.

    The optional arguments preserve the Step 0 function name while allowing the
    Step 4 pipeline to use the question and structured tool metadata.
    """
    selection = select_chart(data, question, metadata or {})
    return selection


def select_chart(
    data: list[dict[str, Any]],
    question: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    context = metadata or {}
    if not data:
        return None
    text = question.lower()
    tool = context.get("tool", "")
    metric = context.get("metric", "")

    if _is_distribution(text, tool, metric):
        return _distribution_chart(data)
    if _is_scatter(text, context):
        return _scatter_chart(data)
    if _is_part_to_whole(text, tool, metric):
        return _doughnut_chart(data, metric)
    if _is_dual_time(text, context):
        return _dual_time_chart(context)
    if _is_ranked(text, context):
        return _ranked_bar_chart(data, context)
    if context.get("ambiguous"):
        return {"chart_options": [_category_bar_chart(data, context), _ranked_bar_chart(data, context)]}
    if _is_category(text, tool, context):
        return _category_bar_chart(data, context)
    if _is_time(data, text, tool):
        return _time_line_chart(data, context)
    if _looks_ambiguous(text, data, context):
        return {"chart_options": [_category_bar_chart(data, context), _ranked_bar_chart(data, context)]}
    return _category_bar_chart(data, context) if _has_dimension(data) else None


def _chart(chart_type: str, justification: str, config: dict[str, Any]) -> dict[str, Any]:
    return {"type": chart_type, "justification": justification, "config": config}


def _value(row: dict[str, Any]) -> float | int | None:
    value = row.get("value")
    return value if isinstance(value, (int, float)) else None


def _label(row: dict[str, Any]) -> Any:
    for key in ("period", "category", "seller_id", "payment_type", "state", "score", "entity", "label"):
        if key in row:
            return row[key]
    return ""


def _dataset(label: str, values: list[Any], axis: str | None = None, color: str = "#2563eb") -> dict[str, Any]:
    result: dict[str, Any] = {"label": label, "data": values, "backgroundColor": color, "borderColor": color}
    if axis:
        result["yAxisID"] = axis
    return result


def _time_line_chart(data: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    labels = [row.get("period", _label(row)) for row in data]
    label = metadata.get("label") or _metric_label(metadata.get("metric", "value"))
    config = {"type": "line", "data": {"labels": labels, "datasets": [_dataset(label, [_value(row) for row in data])]}, "options": {"responsive": True, "scales": {"x": {"title": {"display": True, "text": "Period"}}}}}
    return _chart("line", "A single metric is plotted over time.", config)


def _dual_time_chart(metadata: dict[str, Any]) -> dict[str, Any]:
    series = metadata.get("series", [])
    labels = metadata.get("labels", [])
    datasets = []
    for index, item in enumerate(series[:2]):
        datasets.append(_dataset(item.get("label", f"Metric {index + 1}"), item.get("values", []), "y" if index == 0 else "y1", "#2563eb" if index == 0 else "#dc2626"))
    config = {"type": "line", "data": {"labels": labels, "datasets": datasets}, "options": {"responsive": True, "scales": {"y": {"type": "linear", "position": "left"}, "y1": {"type": "linear", "position": "right", "grid": {"drawOnChartArea": False}}}}}
    return _chart("line", "Two metrics share the same time axis, so separate y-axes preserve their scales.", config)


def _ranked_bar_chart(data: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    descending = metadata.get("sort", "desc") != "asc"
    ordered = sorted(data, key=lambda row: (_value(row) is None, _value(row) or 0), reverse=descending)
    labels = [_label(row) for row in ordered]
    values = [_value(row) for row in ordered]
    config = {"type": "bar", "data": {"labels": labels, "datasets": [_dataset(_metric_label(metadata.get("metric", "value")), values)]}, "options": {"indexAxis": "y", "responsive": True}}
    return _chart("bar", "A horizontal bar chart makes the ranked comparison easy to scan.", config)


def _category_bar_chart(data: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    config = {"type": "bar", "data": {"labels": [_label(row) for row in data], "datasets": [_dataset(_metric_label(metadata.get("metric", "value")), [_value(row) for row in data])]}, "options": {"responsive": True}}
    return _chart("bar", "A vertical bar chart compares the metric across categories or entities.", config)


def _doughnut_chart(data: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    value_key = "share" if any("share" in row for row in data) else "value"
    config = {"type": "doughnut", "data": {"labels": [_label(row) for row in data], "datasets": [_dataset("Payment Share" if value_key == "share" else _metric_label(metric), [row.get(value_key) for row in data], color=["#2563eb", "#dc2626", "#16a34a", "#ca8a04", "#9333ea"]) ]}, "options": {"responsive": True}}
    return _chart("doughnut", "A doughnut chart shows the selected payment metric as parts of a whole.", config)


def _distribution_chart(data: list[dict[str, Any]]) -> dict[str, Any]:
    buckets = {int(row.get("score")): row.get("value", 0) for row in data if row.get("score") is not None}
    scores = [1, 2, 3, 4, 5]
    config = {"type": "bar", "data": {"labels": ["Reviews"], "datasets": [{"label": str(score), "data": [buckets.get(score, 0)], "backgroundColor": color} for score, color in zip(scores, ["#991b1b", "#ea580c", "#ca8a04", "#65a30d", "#15803d"]) ]}, "options": {"indexAxis": "y", "responsive": True, "scales": {"x": {"stacked": True}, "y": {"stacked": True}}}}
    return _chart("bar", "A stacked horizontal bar preserves every review score bucket from 1 through 5.", config)


def _scatter_chart(data: list[dict[str, Any]]) -> dict[str, Any]:
    points = [{"x": row.get("x"), "y": row.get("y")} for row in data if row.get("x") is not None and row.get("y") is not None]
    config = {"type": "scatter", "data": {"datasets": [{"label": "Entity comparison", "data": points, "backgroundColor": "#2563eb"}]}, "options": {"responsive": True}}
    return _chart("scatter", "A scatter chart shows two continuous variables for each entity.", config)


def _is_distribution(text: str, tool: str, metric: str) -> bool:
    return "distribution" in text or tool == "review_analysis" and metric == "distribution"


def _is_scatter(text: str, context: dict[str, Any]) -> bool:
    return " vs " in f" {text} " and bool(context.get("scatter_data"))


def _is_part_to_whole(text: str, tool: str, metric: str) -> bool:
    return "share" in text or metric in {"transaction_share", "value_share"} or tool == "payment_breakdown" and metric in {"value_by_type", "value_share", "transaction_share"}


def _is_dual_time(text: str, context: dict[str, Any]) -> bool:
    return bool(context.get("series")) and len(context["series"]) >= 2 and _is_time([], text, "")


def _is_ranked(text: str, context: dict[str, Any]) -> bool:
    return any(word in text for word in ("top ", "bottom ", "worst", "best", "rank")) or bool(context.get("ranking"))


def _is_category(text: str, tool: str, context: dict[str, Any]) -> bool:
    return "categor" in text or tool in {"product_performance", "review_analysis"} and context.get("metric") in {"revenue", "orders", "review_score", "freight", "category"}


def _is_time(data: list[dict[str, Any]], text: str, tool: str) -> bool:
    return any("period" in row for row in data) or tool == "order_trends" or any(word in text for word in ("monthly", "daily", "yearly", "over time", "trend"))


def _has_dimension(data: list[dict[str, Any]]) -> bool:
    return any(any(key in row for key in ("category", "seller_id", "payment_type", "state", "score")) for row in data)


def _looks_ambiguous(text: str, data: list[dict[str, Any]], context: dict[str, Any]) -> bool:
    return "compare" in text and not _is_time(data, text, context.get("tool", ""))


def _metric_label(metric: str) -> str:
    return {"revenue": "Revenue", "orders": "Orders", "freight": "Freight", "review_score": "Average Review Score", "delivery_delay": "Delivery Delay (days)", "on_time_rate": "On-time Rate (%)", "value_share": "Payment Share", "transaction_share": "Transaction Share"}.get(metric, metric.replace("_", " ").title())
