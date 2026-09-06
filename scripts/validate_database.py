"""Run representative integrity and analytical checks against Olist SQLite."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.database.connection import get_connection
from app.database.models import REQUIRED_TABLES


def _scalar(connection: sqlite3.Connection, sql: str) -> int | float:
    return connection.execute(sql).fetchone()[0]


def validate_database() -> dict[str, object]:
    with get_connection() as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        missing = sorted(set(REQUIRED_TABLES) - set(tables))
        if missing:
            raise RuntimeError(f"Missing required tables: {', '.join(missing)}")
        counts = {table: int(_scalar(connection, f"SELECT COUNT(*) FROM {table}")) for table in REQUIRED_TABLES}
        checks = {
            "orders_to_items": int(_scalar(connection, "SELECT COUNT(*) FROM orders o JOIN order_items i ON i.order_id = o.order_id")),
            "orders_to_payments": int(_scalar(connection, "SELECT COUNT(*) FROM orders o JOIN order_payments p ON p.order_id = o.order_id")),
            "orders_to_reviews": int(_scalar(connection, "SELECT COUNT(*) FROM orders o JOIN order_reviews r ON r.order_id = o.order_id")),
            "orders_to_customers": int(_scalar(connection, "SELECT COUNT(*) FROM orders o JOIN customers c ON c.customer_id = o.customer_id")),
            "items_to_products": int(_scalar(connection, "SELECT COUNT(*) FROM order_items i JOIN products p ON p.product_id = i.product_id")),
            "items_to_sellers": int(_scalar(connection, "SELECT COUNT(*) FROM order_items i JOIN sellers s ON s.seller_id = i.seller_id")),
            "products_to_english_categories": int(_scalar(connection, "SELECT COUNT(*) FROM products p JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name")),
            "sellers_to_geolocation": int(_scalar(connection, "SELECT COUNT(*) FROM sellers s JOIN geolocation g ON g.geolocation_zip_code_prefix = s.seller_zip_code_prefix")),
            "customers_to_geolocation": int(_scalar(connection, "SELECT COUNT(*) FROM customers c JOIN geolocation g ON g.geolocation_zip_code_prefix = c.customer_zip_code_prefix")),
            "date_filter_orders": int(_scalar(connection, "SELECT COUNT(*) FROM orders WHERE order_purchase_timestamp >= '2017-01-01T00:00:00' AND order_purchase_timestamp < '2018-01-01T00:00:00'")),
            "revenue_from_items": float(_scalar(connection, "SELECT COALESCE(SUM(price), 0) FROM order_items")),
            "total_payment_value": float(_scalar(connection, "SELECT COALESCE(SUM(payment_value), 0) FROM order_payments")),
            "translated_categories": int(_scalar(connection, "SELECT COUNT(*) FROM product_category_name_translation")),
        }
    return {"tables": tables, "row_counts": counts, "checks": checks}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-path", type=Path)
    args = parser.parse_args()
    if args.database_path:
        import os
        os.environ["DATABASE_PATH"] = str(args.database_path)
    report = validate_database()
    print("Tables:", ", ".join(report["tables"]))
    print("Row counts:", report["row_counts"])
    for name, value in report["checks"].items():
        print(f"{name}: {value}")


if __name__ == "__main__":
    main()