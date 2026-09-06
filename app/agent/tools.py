"""The allowlisted Step 2 tools and their Groq function schemas."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from app.mcp_server.tools.delivery import delivery_performance
from app.mcp_server.tools.orders import order_trends
from app.mcp_server.tools.payments import payment_breakdown
from app.mcp_server.tools.products import product_performance
from app.mcp_server.tools.reviews import review_analysis
from app.mcp_server.tools.sellers import seller_performance

TOOL_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "order_trends": order_trends,
    "product_performance": product_performance,
    "seller_performance": seller_performance,
    "review_analysis": review_analysis,
    "payment_breakdown": payment_breakdown,
    "delivery_performance": delivery_performance,
}

TOOL_DEFINITIONS = [
    {"type": "function", "function": {"name": "order_trends", "description": "Order counts, item revenue, delivery delay, or on-time rate over day/month/year periods with optional ISO date filters.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["revenue", "orders", "delivery_delay", "on_time_rate"]}, "from_date": {"type": ["string", "null"]}, "to_date": {"type": ["string", "null"]}, "granularity": {"type": "string", "enum": ["day", "month", "year"]}}, "required": []}}},
    {"type": "function", "function": {"name": "product_performance", "description": "Revenue, distinct order volume, review score, or freight by English-translated product category; supports category/date/ranking filters.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["revenue", "orders", "review_score", "freight"]}, "category": {"type": ["string", "null"]}, "from_date": {"type": ["string", "null"]}, "to_date": {"type": ["string", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "sort": {"type": "string", "enum": ["asc", "desc"]}}, "required": []}}},
    {"type": "function", "function": {"name": "seller_performance", "description": "Seller revenue, average rating, or delivery speed with seller state, date, limit, and sort filters.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["revenue", "review_score", "delivery_speed"]}, "state": {"type": ["string", "null"]}, "from_date": {"type": ["string", "null"]}, "to_date": {"type": ["string", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "sort": {"type": "string", "enum": ["asc", "desc"]}}, "required": []}}},
    {"type": "function", "function": {"name": "review_analysis", "description": "Review score distribution with explicit 1-5 buckets, averages, category/seller scores, or response time in hours.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["distribution", "average", "category", "seller", "response_time"]}, "category": {"type": ["string", "null"]}, "seller_id": {"type": ["string", "null"]}, "from_date": {"type": ["string", "null"]}, "to_date": {"type": ["string", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "sort": {"type": "string", "enum": ["asc", "desc"]}}, "required": []}}},
    {"type": "function", "function": {"name": "payment_breakdown", "description": "Payment value, transaction share, payment-value share, installments, or monthly payment value by data-driven payment type.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["value_by_type", "transaction_share", "value_share", "installments", "value_by_period"]}, "from_date": {"type": ["string", "null"]}, "to_date": {"type": ["string", "null"]}}, "required": []}}},
    {"type": "function", "function": {"name": "delivery_performance", "description": "Delivery delay or on-time rate by customer state, excluding orders without actual delivery timestamps.", "parameters": {"type": "object", "properties": {"metric": {"type": "string", "enum": ["delay", "on_time_rate"]}, "state": {"type": ["string", "null"]}, "from_date": {"type": ["string", "null"]}, "to_date": {"type": ["string", "null"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}, "sort": {"type": "string", "enum": ["asc", "desc"]}}, "required": []}}},
]


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    function = TOOL_FUNCTIONS.get(name)
    if function is None:
        return {"success": False, "error": {"code": "UNKNOWN_TOOL", "message": f"Unknown analytics tool: {name}"}}
    try:
        return await asyncio.to_thread(function, **arguments)
    except TypeError as exc:
        return {"success": False, "error": {"code": "INVALID_TOOL_ARGUMENTS", "message": str(exc)}}
    except Exception:
        return {"success": False, "error": {"code": "TOOL_FAILURE", "message": f"Tool {name} failed."}}