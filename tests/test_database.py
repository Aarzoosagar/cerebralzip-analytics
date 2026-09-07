"""Focused Step 1 database tests using tiny CSV fixtures."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

import pytest

from app.database.connection import get_connection
from app.database.loader import load_olist_dataset
from app.database.models import REQUIRED_TABLES, SCHEMA_SQL
from app.database import bootstrap


def _write_csv(root: Path, filename: str, headers: list[str], rows: list[list[object]]) -> None:
    with (root / filename).open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(rows)


@pytest.fixture
def fixture_data(tmp_path: Path) -> Path:
    _write_csv(tmp_path, "olist_customers_dataset.csv", ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"], [["c1", "u1", 100, "city", "ST"]])
    _write_csv(tmp_path, "olist_geolocation_dataset.csv", ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"], [[100, 1.0, 2.0, "city", "ST"]])
    _write_csv(tmp_path, "olist_sellers_dataset.csv", ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"], [["s1", 100, "city", "ST"]])
    _write_csv(tmp_path, "olist_products_dataset.csv", ["product_id", "product_category_name", "product_name_lenght", "product_description_lenght", "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm"], [["p1", "cat", 4, 10, 1, 100, 1, 2, 3]])
    _write_csv(tmp_path, "product_category_name_translation.csv", ["product_category_name", "product_category_name_english"], [["cat", "category"]])
    _write_csv(tmp_path, "olist_orders_dataset.csv", ["order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date"], [["o1", "c1", "delivered", "2017-01-01 10:00:00", "2017-01-01 11:00:00", "2017-01-02 10:00:00", "2017-01-03 10:00:00", "2017-01-10"]])
    _write_csv(tmp_path, "olist_order_items_dataset.csv", ["order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value"], [["o1", 1, "p1", "s1", "2017-01-02 12:00:00", 10.5, 2.0]])
    _write_csv(tmp_path, "olist_order_payments_dataset.csv", ["order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value"], [["o1", 1, "credit_card", 1, 12.5]])
    _write_csv(tmp_path, "olist_order_reviews_dataset.csv", ["review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp"], [["r1", "o1", 5, "title", "message", "2017-01-04", "2017-01-05 10:00:00"]])
    return tmp_path


def test_missing_csv_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "missing.db"))
    with pytest.raises(FileNotFoundError, match="Missing required Olist CSV files"):
        load_olist_dataset(tmp_path)


def test_schema_loader_relationships_and_translation(fixture_data: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", str(fixture_data / "test.db"))
    counts = load_olist_dataset(fixture_data)
    assert counts["orders"] == 1
    with get_connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM orders JOIN order_items USING (order_id)").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM order_items JOIN products USING (product_id)").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM order_items JOIN sellers USING (seller_id)").fetchone()[0] == 1
        category = connection.execute("SELECT product_id, product_category_name, product_category_name_english FROM products JOIN product_category_name_translation USING (product_category_name)").fetchone()
        assert tuple(category) == ("p1", "cat", "category")


def test_ensure_database_loads_missing_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "missing.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    data_dir = tmp_path / "data"
    calls: list[str] = []
    monkeypatch.setattr(bootstrap, "_download_dataset", lambda root: calls.append(str(root)))
    monkeypatch.setattr(bootstrap, "load_olist_dataset", lambda root: {"orders": 1})
    result = bootstrap.ensure_database(data_dir)
    assert result == {"orders": 1}
    assert calls == [str(data_dir)]


def test_ensure_database_loads_empty_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "empty.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
    monkeypatch.setattr(bootstrap, "load_olist_dataset", lambda root: {"orders": 1})
    monkeypatch.setattr(bootstrap, "_download_dataset", lambda root: None)
    assert bootstrap.ensure_database(tmp_path / "data") == {"orders": 1}


def test_ensure_database_skips_initialized_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database_path = tmp_path / "ready.db"
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute("INSERT INTO customers VALUES ('c1', 'u1', 1, 'city', 'ST')")
        connection.execute("INSERT INTO orders VALUES ('o1', 'c1', 'delivered', '2017-01-01', NULL, NULL, NULL, '2017-01-02')")
    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(REQUIRED_TABLES).issubset(tables)
    monkeypatch.setattr(bootstrap, "load_olist_dataset", lambda root: pytest.fail("initialized database was reloaded"))
    assert bootstrap.ensure_database(tmp_path / "unused") is None