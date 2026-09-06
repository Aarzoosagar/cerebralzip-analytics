"""Official MCP 2.x server exposing the six Olist analytics tools."""

from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

from app.mcp_server.tools.delivery import delivery_performance
from app.mcp_server.tools.orders import order_trends
from app.mcp_server.tools.payments import payment_breakdown
from app.mcp_server.tools.products import product_performance
from app.mcp_server.tools.reviews import review_analysis
from app.mcp_server.tools.sellers import seller_performance

mcp_server = MCPServer("cerebralzip-analytics", version="0.2.0", description="Controlled analytics tools over the CerebralZip Olist SQLite database.")

_TOOLS = (
    (order_trends, "Order trends by period. Supports revenue, orders, delivery_delay, and on_time_rate metrics with day, month, or year granularity."),
    (product_performance, "Product category performance using English category translations. Supports revenue, orders, review_score, freight, date filters, ranking, and limits."),
    (seller_performance, "Seller performance by revenue, review score, or delivery speed, with state, date, ranking, and limit filters."),
    (review_analysis, "Review score distribution, averages, category or seller scores, and response-time analysis."),
    (payment_breakdown, "Payment value, transaction share, value share, installments, or monthly payment value by data-driven payment type."),
    (delivery_performance, "Delivery delay or on-time rate by customer state. Missing actual delivery timestamps are excluded."),
)

for function, description in _TOOLS:
    mcp_server.add_tool(function, description=description, structured_output=True)


def create_server() -> MCPServer:
    """Return the configured MCP 2.x server without opening a database connection."""
    return mcp_server


async def run_stdio() -> None:
    """Run the official MCP stdio transport."""
    await mcp_server.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(run_stdio())
