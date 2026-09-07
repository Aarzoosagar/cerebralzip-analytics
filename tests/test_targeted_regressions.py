from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from app.agent.fallback_agent import FallbackAgent
from app.analytics.response import build_analytics_response
from app.database.models import SCHEMA_SQL
from app.mcp_server.tools.payments import payment_breakdown
from app.mcp_server.tools.products import product_performance
from app.mcp_server.tools.reviews import review_analysis


def _controlled_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "controlled.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.executemany(
            "INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
            [("c1", "u1", 1, "city", "SP"), ("c2", "u2", 2, "city", "RJ")],
        )
        connection.executemany(
            "INSERT INTO sellers VALUES (?, ?, ?, ?)",
            [("s1", 1, "seller", "SP"), ("s2", 2, "seller", "RJ")],
        )
        connection.executemany(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [("p1", "cat", 1, 1, 1, 1, 1, 1, 1), ("p2", "cat", 1, 1, 1, 1, 1, 1, 1), ("p3", "other", 1, 1, 1, 1, 1, 1, 1)],
        )
        connection.executemany(
            "INSERT INTO product_category_name_translation VALUES (?, ?)",
            [("cat", "electronics"), ("other", "books")],
        )
        connection.executemany(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("o1", "c1", "delivered", "2017-01-01T10:00:00", None, None, "2017-01-03T10:00:00", "2017-01-02T10:00:00"),
                ("o2", "c2", "delivered", "2017-01-02T10:00:00", None, None, "2017-01-04T10:00:00", "2017-01-03T10:00:00"),
            ],
        )
        connection.executemany(
            "INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("o1", 1, "p1", "s1", "2017-01-02T10:00:00", 10, 1),
                ("o1", 2, "p2", "s1", "2017-01-02T10:00:00", 20, 1),
                ("o2", 1, "p3", "s2", "2017-01-03T10:00:00", 30, 1),
            ],
        )
        connection.executemany(
            "INSERT INTO order_payments VALUES (?, ?, ?, ?, ?)",
            [("o1", 1, "credit_card", 1, 70), ("o1", 2, "boleto", 1, 30), ("o2", 1, "voucher", 1, 10)],
        )
        connection.executemany(
            "INSERT INTO order_reviews VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(1, "r1", "o1", 1, None, None, "2017-01-04T00:00:00", "2017-01-05T00:00:00"), (2, "r2", "o2", 5, None, None, "2017-01-05T00:00:00", "2017-01-06T00:00:00")],
        )
        connection.commit()


def test_worst_and_best_rated_sort_in_the_expected_direction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(tool: str, arguments: dict) -> dict:
        return {"success": True, "data": [{"seller_id": "s1", "value": 1}], "metadata": {"metric": "review_score"}}

    monkeypatch.setattr("app.agent.fallback_agent.call_tool", fake_call)
    worst = asyncio.run(FallbackAgent().analyze("worst rated sellers"))
    best = asyncio.run(FallbackAgent().analyze("best rated sellers"))
    assert worst["tool_calls"][0]["arguments"]["sort"] == "asc"
    assert best["tool_calls"][0]["arguments"]["sort"] == "desc"


def test_delivery_worst_remains_descending(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(tool: str, arguments: dict) -> dict:
        return {"success": True, "data": [{"state": "SP", "value": 2}], "metadata": {"metric": "delay"}}

    monkeypatch.setattr("app.agent.fallback_agent.call_tool", fake_call)
    result = asyncio.run(FallbackAgent().analyze("states with worst delivery delays"))
    assert result["tool_calls"][0]["arguments"]["sort"] == "desc"


def test_credit_card_boleto_comparison_filters_and_charts_only_two_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _controlled_database(tmp_path, monkeypatch)
    result = asyncio.run(FallbackAgent().analyze("credit card vs boleto share"))
    assert result["tool_calls"][0]["arguments"]["payment_types"] == ["credit_card", "boleto"]
    payment_result = result["results"][0]["result"]
    assert {row["payment_type"] for row in payment_result["data"]} == {"credit_card", "boleto"}
    response = build_analytics_response("credit card vs boleto share", result)
    assert response["chart"]["type"] == "doughnut"
    assert response["chart"]["config"]["data"]["labels"] == ["credit_card", "boleto"]
    assert "credit_card" in response["insight"] or "boleto" in response["insight"]


def test_review_averages_do_not_multiply_duplicate_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _controlled_database(tmp_path, monkeypatch)
    category = product_performance(metric="review_score", category="electronics", limit=10)
    translated_category = review_analysis(metric="category", category="electronics", limit=10)
    seller = review_analysis(metric="seller", seller_id="s1", limit=10)
    assert category["data"] == [{"category": "electronics", "value": 1.0}]
    assert translated_category["data"] == [{"category": "electronics", "value": 1.0}]
    assert seller["data"] == [{"seller_id": "s1", "value": 1.0}]


def test_generic_payment_breakdown_still_returns_all_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _controlled_database(tmp_path, monkeypatch)
    result = payment_breakdown(metric="value_share")
    assert {row["payment_type"] for row in result["data"]} == {"credit_card", "boleto", "voucher"}
