"""Step 4 pipeline from Step 3 agent results to chart and insight output."""

from __future__ import annotations

from typing import Any

from app.analytics.chart_selector import select_chart_config
from app.analytics.insight import generate_insight


def build_analytics_response(question: str, agent_response: dict[str, Any]) -> dict[str, Any]:
    """Create the stable analytics response consumed by a future API/frontend."""
    if not isinstance(agent_response, dict):
        return _unsupported(question, "The agent returned an invalid response.")
    agent_error = agent_response.get("error") or {}
    if agent_error.get("code") in {"UNSUPPORTED_QUERY", "UNSUPPORTED_QUESTION"}:
        return _unsupported(question, agent_error.get("message", "The question is not supported."))

    successful = []
    failed = []
    for item in agent_response.get("results", []):
        result = item.get("result", {})
        if result.get("success") and result.get("data"):
            successful.append((item.get("tool", ""), result))
        else:
            failed.append((item.get("tool", ""), result))
    if not successful:
        if agent_error.get("code") == "NO_RESULTS" or any((result.get("error") or {}).get("code") == "NO_RESULTS" for _, result in failed):
            return {"success": True, "question": question, "chart": None, "insight": None, "message": "No chart available because the selected filters returned no data.", "metadata": {"row_count": 0}}
        return {"success": False, "question": question, "chart": None, "insight": None, "error": agent_error or {"code": "NO_RESULTS", "message": "No usable analytics results were returned."}}

    tool, result = successful[0]
    metadata = dict(result.get("metadata") or {})
    metadata.update({"tool": tool, "row_count": len(result.get("data", []))})
    context: dict[str, Any] = {**metadata, "ranking": _is_ranking(question, agent_response), "sort": _sort_from_calls(agent_response, tool)}
    data = result["data"]

    if len(successful) >= 2 and _is_state_comparison_query(question, successful):
        context.update(_state_comparison_context(successful))
    elif len(successful) >= 2 and _is_category_comparison_query(question, successful):
        context.update(_category_comparison_context(successful))
    elif len(successful) >= 2 and _is_dual_time_query(question, successful):
        context.update(_time_series_context(successful))
    elif len(successful) >= 2 and _is_scatter_comparison(question):
        scatter_data = _scatter_data(successful)
        if scatter_data:
            data = scatter_data
            context["scatter_data"] = scatter_data
    chart = select_chart_config(data, question, context)
    if chart is None:
        return {"success": True, "question": question, "chart": None, "insight": None, "message": "No chart available because the returned data shape is not suitable for a supported visualization.", "metadata": metadata}
    if "chart_options" in chart:
        options = chart["chart_options"]
        return {"success": True, "question": question, "chart": None, "chart_options": options[:2], "insight": generate_insight(question, data, context), "metadata": metadata}
    response: dict[str, Any] = {"success": True, "question": question, "agent_mode": agent_response.get("agent_mode"), "tool_calls": agent_response.get("tool_calls", []), "chart": chart, "insight": generate_insight(question, data, context), "metadata": metadata}
    if failed:
        response["metadata"]["partial_failures"] = [name for name, _ in failed]
        response["message"] = "Some requested sources failed; the chart uses the successful results."
    return response


def _is_category_comparison_query(question: str, successful: list[tuple[str, dict[str, Any]]]) -> bool:
    text = question.lower()
    return "top" in text and "categor" in text and any(tool == "product_performance" for tool, _ in successful) and any(tool == "review_analysis" for tool, _ in successful)


def _is_state_comparison_query(question: str, successful: list[tuple[str, dict[str, Any]]]) -> bool:
    text = question.lower()
    return "state" in text and any(tool == "delivery_performance" for tool, _ in successful) and any(tool == "review_analysis" for tool, _ in successful)


def _category_comparison_context(successful: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    order_result = next(result for tool, result in successful if tool == "product_performance")
    category_rows = order_result["data"][:5]
    review_scores = {}
    for tool, result in successful:
        if tool == "review_analysis":
            for row in result.get("data", []):
                if row.get("category") is not None:
                    review_scores[str(row["category"])] = row.get("value")
    labels = [str(row["category"]) for row in category_rows]
    return {"category_series": [{"label": "Order Volume", "values": [row.get("value") for row in category_rows]}, {"label": "Average Review Score", "values": [review_scores.get(label) for label in labels]}], "category_labels": labels}


def _state_comparison_context(successful: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    delay_result = next(result for tool, result in successful if tool == "delivery_performance")
    state_rows = delay_result["data"][:5]
    review_scores = {}
    for tool, result in successful:
        if tool == "review_analysis":
            for row in result.get("data", []):
                if row.get("state") is not None:
                    review_scores[str(row["state"])] = row.get("value")
    labels = [str(row["state"]) for row in state_rows]
    return {"state_series": [{"label": "Delivery Delay", "values": [row.get("value") for row in state_rows]}, {"label": "Average Review Score", "values": [review_scores.get(label) for label in labels]}], "state_labels": labels}


def _unsupported(question: str, message: str) -> dict[str, Any]:
    return {"success": False, "question": question, "chart": None, "insight": None, "error": {"code": "UNSUPPORTED_QUERY", "message": message}}


def _is_ranking(question: str, agent_response: dict[str, Any]) -> bool:
    text = question.lower()
    return any(word in text for word in ("top ", "bottom ", "worst", "best", "rank")) or bool((agent_response.get("analysis") or {}).get("suggested_analysis", {}).get("ranking"))


def _sort_from_calls(agent_response: dict[str, Any], tool: str) -> str:
    for call in agent_response.get("tool_calls", []):
        if call.get("tool") == tool:
            return call.get("arguments", {}).get("sort", "desc")
    return "desc"


def _is_dual_time_query(question: str, successful: list[tuple[str, dict[str, Any]]]) -> bool:
    return " and " in question.lower() and all(result.get("data") and all("period" in row for row in result.get("data", [])) for _, result in successful[:2])


def _time_series_context(successful: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    series = []
    labels: list[str] = []
    for tool, result in successful[:2]:
        rows = result["data"]
        by_period = {row.get("period"): row.get("value") for row in rows}
        labels.extend(str(row.get("period")) for row in rows if row.get("period") not in labels)
        series.append({"label": (result.get("metadata") or {}).get("metric", tool).replace("_", " ").title(), "values_by_period": by_period, "values": []})
    labels.sort()
    for item in series:
        item["values"] = [item["values_by_period"].get(label) for label in labels]
        item.pop("values_by_period", None)
    return {"series": series, "labels": labels}


def _scatter_data(successful: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    first = {_row_label(row): row.get("value") for row in successful[0][1].get("data", [])}
    second = {_row_label(row): row.get("value") for row in successful[1][1].get("data", [])}
    return [{"entity": label, "x": first[label], "y": second[label]} for label in first.keys() & second.keys() if first[label] is not None and second[label] is not None]


def _is_scatter_comparison(question: str) -> bool:
    text = question.lower()
    return " vs " in f" {text} " or "versus" in text or "relate to" in text or "relationship" in text


def _row_label(row: dict[str, Any]) -> str:
    for key in ("state", "seller_id", "category", "entity", "label"):
        if key in row:
            return str(row[key])
    return ""
