"""Explicit, repeatable loader for the Olist CSV dataset."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from app.database.connection import get_connection
from app.database.models import SCHEMA_SQL

CSV_FILES = {
    "customers": ("olist_customers_dataset.csv", ("customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state")),
    "geolocation": ("olist_geolocation_dataset.csv", ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state")),
    "orders": ("olist_orders_dataset.csv", ("order_id", "customer_id", "order_status", "order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date")),
    "order_items": ("olist_order_items_dataset.csv", ("order_id", "order_item_id", "product_id", "seller_id", "shipping_limit_date", "price", "freight_value")),
    "order_payments": ("olist_order_payments_dataset.csv", ("order_id", "payment_sequential", "payment_type", "payment_installments", "payment_value")),
    "order_reviews": ("olist_order_reviews_dataset.csv", ("review_id", "order_id", "review_score", "review_comment_title", "review_comment_message", "review_creation_date", "review_answer_timestamp")),
    "products": ("olist_products_dataset.csv", ("product_id", "product_category_name", "product_name_lenght", "product_description_lenght", "product_photos_qty", "product_weight_g", "product_length_cm", "product_height_cm", "product_width_cm")),
    "sellers": ("olist_sellers_dataset.csv", ("seller_id", "seller_zip_code_prefix", "seller_city", "seller_state")),
    "product_category_name_translation": ("product_category_name_translation.csv", ("product_category_name", "product_category_name_english")),
}
DATE_COLUMNS = {column for _, columns in CSV_FILES.values() for column in columns if "date" in column or "timestamp" in column}


def _value(value: Any) -> Any:
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def _normalized_rows(frame: pd.DataFrame, columns: tuple[str, ...]):
    for row in frame.loc[:, columns].itertuples(index=False, name=None):
        yield tuple(_value(value) for value in row)


def _read_csv(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(path, usecols=list(columns), low_memory=False)
    for column in columns:
        if column in DATE_COLUMNS:
            frame[column] = pd.to_datetime(frame[column], errors="raise").dt.strftime("%Y-%m-%dT%H:%M:%S")
    return frame


def _insert_frame(connection: sqlite3.Connection, table: str, frame: pd.DataFrame, columns: tuple[str, ...]) -> int:
    if table == "order_reviews":
        frame = frame.copy()
        frame.insert(0, "review_row_id", range(1, len(frame) + 1))
        columns = ("review_row_id",) + columns
    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        _normalized_rows(frame, columns),
    )
    return len(frame)


def load_olist_dataset(data_dir: str | Path = "data") -> dict[str, int]:
    """Drop and recreate all analytical tables, then load every CSV once."""
    root = Path(data_dir)
    missing = [filename for filename, _ in CSV_FILES.values() if not (root / filename).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing required Olist CSV files in {root}: {', '.join(missing)}")
    counts: dict[str, int] = {}
    with get_connection() as connection:
        connection.executescript(SCHEMA_SQL)
        for table in ("customers", "geolocation", "sellers", "products", "product_category_name_translation", "orders", "order_items", "order_payments", "order_reviews"):
            filename, columns = CSV_FILES[table]
            frame = _read_csv(root / filename, columns)
            counts[table] = _insert_frame(connection, table, frame, columns)
            print(f"Loaded {counts[table]:,} rows into {table} from {filename}")
        connection.commit()
    return counts
