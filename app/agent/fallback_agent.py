"""Deterministic rule-based fallback agent."""

from __future__ import annotations

import re
from typing import Any

from app.agent.interface import ILLMAgent
from app.agent.tools import call_tool


class FallbackAgent(ILLMAgent):
    """Maps common assignment questions to structured Step 2 calls."""

    async def analyze(self, question: str) -> dict[str, Any]:
        original = question.strip()
        base = {"success": False, "agent_mode": "fallback", "question": original, "tool_calls": [], "results": []}
        if not original:
            return {**base, "error": {"code": "INVALID_PARAMETER", "message": "question must not be empty."}}
        text = original.lower()
        dates, assumptions = _date_parameters(text)
        calls: list[tuple[str, dict[str, Any]]] = []
        if ("delivery" in text or "delay" in text) and ("review" in text or "rating" in text) and "state" not in text and _is_delivery_review_comparison(text):
            calls.extend([
                ("seller_performance", {"metric": "delivery_speed", "state": None, "limit": 100, "sort": "asc", **dates}),
                ("seller_performance", {"metric": "review_score", "state": None, "limit": 100, "sort": "desc", **dates}),
            ])
        elif ("delay" in text or "delivery" in text) and ("review" in text or "rating" in text) and "state" in text:
            calls.append(("delivery_performance", {"metric": "delay", "state": None, "limit": _limit(text, default=5), "sort": "desc", **dates}))
        elif "order" in text and ("review" in text or "rating" in text) and any(word in text for word in ("monthly", "by month", "month")):
            calls.extend([
                ("order_trends", {"metric": "orders", "granularity": "month", **dates}),
                ("review_analysis", {"metric": "average", "granularity": "month", "category": None, "seller_id": None, "limit": 100, "sort": "asc", **dates}),
            ])
        elif "payment" in text or "credit card" in text or "boleto" in text or "installment" in text:
            metric = "value_share" if "share" in text or "vs" in text or " versus " in text else "value_by_type"
            payment_types = ["credit_card", "boleto"] if "credit card" in text and "boleto" in text else None
            calls.append(("payment_breakdown", {"metric": metric, "payment_types": payment_types, **dates}))
        elif "delivery" in text or "on-time" in text or "delay" in text or "shipping" in text:
            metric = "on_time_rate" if "on-time" in text or "on time" in text else "delay"
            calls.append(("delivery_performance", {"metric": metric, "state": _state(text), "limit": _limit(text), "sort": _sort(text, descending=metric == "on_time_rate"), **dates}))
        elif "review" in text or "rating" in text or "rated" in text:
            if "distribution" in text or "score distribution" in text:
                metric = "distribution"
            elif "category" in text or "categories" in text:
                metric = "category"
            elif "seller" in text:
                metric = "seller"
            else:
                metric = "average"
            calls.append(("review_analysis", {"metric": metric, "category": _category(text), "seller_id": None, "limit": _limit(text), "sort": _sort(text), **dates}))
        elif "seller" in text:
            calls.append(("seller_performance", {"metric": "review_score" if "rating" in text or "rated" in text else "delivery_speed" if "speed" in text or "faster" in text else "revenue", "state": _state(text), "limit": _limit(text), "sort": _sort(text), **dates}))
        elif "category" in text or "product" in text:
            calls.append(("product_performance", {"metric": "freight" if "freight" in text else "review_score" if "review" in text or "rating" in text else "orders" if "order volume" in text or "number of orders" in text else "revenue", "category": _category(text), "limit": _limit(text), "sort": _sort(text), **dates}))
        elif "order" in text or "revenue" in text or "sales" in text:
            metric = "orders" if "order" in text and "revenue" not in text else "delivery_delay" if "delay" in text else "revenue"
            granularity = "day" if "daily" in text or "by day" in text else "year" if "yearly" in text or "annual" in text else "month"
            calls.append(("order_trends", {"metric": metric, "granularity": granularity, **dates}))
        else:
            return {**base, "error": {"code": "UNSUPPORTED_QUESTION", "message": "The fallback agent could not identify an analytics domain."}}

        # Resolve the assignment's genuinely multi-step top-category comparison.
        if "top" in text and "categor" in text and "review" in text:
            calls = [("product_performance", {"metric": "orders", "limit": _limit(text, default=5), "sort": "desc", "category": None, **dates})]
        for tool, arguments in calls:
            base["tool_calls"].append({"tool": tool, "arguments": arguments})
            result = await call_tool(tool, arguments)
            base["results"].append({"tool": tool, "result": result})
            if tool == "product_performance" and "top" in text and "categor" in text and "review" in text and result.get("success"):
                for row in result["data"]:
                    category_call = {"metric": "category", "category": row["category"], "seller_id": None, "limit": 1, "sort": "desc", **dates}
                    base["tool_calls"].append({"tool": "review_analysis", "arguments": category_call})
                    base["results"].append({"tool": "review_analysis", "result": await call_tool("review_analysis", category_call)})
            if tool == "delivery_performance" and _is_state_review_comparison(text) and result.get("success"):
                state_call = {"metric": "average", "state": None, "group_by_state": True, "category": None, "seller_id": None, "limit": 100, "sort": "desc", **dates}
                base["tool_calls"].append({"tool": "review_analysis", "arguments": state_call})
                base["results"].append({"tool": "review_analysis", "result": await call_tool("review_analysis", state_call)})
        succeeded = [item for item in base["results"] if item["result"].get("success")]
        failed = [item for item in base["results"] if not item["result"].get("success")]
        if not succeeded:
            base["error"] = {"code": failed[0]["result"].get("error", {}).get("code", "TOOL_FAILURE"), "message": "No analytics tool returned usable results."}
        else:
            base["success"] = True
            base["analysis"] = {"interpretation": original, "assumptions": assumptions, "suggested_analysis": _suggested(text)}
            base["chart_hint"] = {"type": "bar", "reason": "Fallback agent always uses a bar chart."}
            if failed:
                base["analysis"]["partial_failure"] = True
        return base


def _date_parameters(text: str) -> tuple[dict[str, str], list[str]]:
    year = re.search(r"\b(20\d{2})\b", text)
    if "first half" in text and year:
        return {"from_date": f"{year.group(1)}-01-01", "to_date": f"{year.group(1)}-06-30"}, []
    if "last year" in text:
        return {"from_date": "2017-01-01", "to_date": "2017-12-31"}, []
    if year:
        return {"from_date": f"{year.group(1)}-01-01", "to_date": f"{year.group(1)}-12-31"}, []
    return {}, ["No date range was specified, so the full available dataset was used."]


def _limit(text: str, default: int = 20) -> int:
    match = re.search(r"\b(?:top|bottom|limit)\s+(\d+)\b", text)
    return min(int(match.group(1)), 100) if match else default


def _sort(text: str, descending: bool = True) -> str:
    if "rated" in text or "review score" in text or "rating" in text:
        if "worst" in text or "lowest" in text or "ascending" in text:
            return "asc"
        if "best" in text or "highest" in text:
            return "desc"
    if "delivery" in text or "delay" in text:
        if "worst" in text or "longest" in text:
            return "desc"
        if "shortest" in text or "fastest" in text:
            return "asc"
    if "ascending" in text or "lowest" in text:
        return "asc"
    return "desc" if descending else "asc"


def _is_delivery_review_comparison(text: str) -> bool:
    relationship_intent = (
        " vs " in f" {text} "
        or "versus" in text
        or "relate to" in text
        or "relationship" in text
        or "associated" in text
        or "lead to" in text
        or "get better" in text
        or "rated better" in text
    )
    speed_intent = "faster" in text or "delivery speed" in text or "fast delivery" in text
    return relationship_intent and speed_intent


def _is_state_review_comparison(text: str) -> bool:
    if "state" not in text or not ("review" in text or "rating" in text):
        return False
    return _is_delivery_review_comparison(text) or " + " in text or "how do" in text and "compare" in text


def _state(text: str) -> str | None:
    if "são paulo" in text or "sao paulo" in text or re.search(r"\bsp\b", text):
        return "SP"
    match = re.search(r"\b([a-z]{2})\b", text)
    return match.group(1).upper() if match and match.group(1).upper() in {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"} else None


def _category(text: str) -> str | None:
    known = ("electronics", "computers", "health_beauty", "sports_leisure", "furniture_decor", "watches_gifts")
    return next((category for category in known if category.replace("_", " ") in text or category in text), None)


def _suggested(text: str) -> dict[str, bool]:
    return {"time_based": any(word in text for word in ("monthly", "daily", "year", "trend")), "ranking": "top" in text or "worst" in text, "category_comparison": "category" in text, "part_to_whole": "share" in text, "distribution": "distribution" in text}
