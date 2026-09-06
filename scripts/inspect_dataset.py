"""Inspect Olist CSV schemas, keys, relationships, and timestamp ranges."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

CSV_FILES = {
    "customers": "olist_customers_dataset.csv", "geolocation": "olist_geolocation_dataset.csv",
    "orders": "olist_orders_dataset.csv", "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv", "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv", "sellers": "olist_sellers_dataset.csv",
    "product_category_name_translation": "product_category_name_translation.csv",
}
RELATIONSHIPS = (
    ("orders", "order_id", "order_items", "order_id"), ("orders", "order_id", "order_payments", "order_id"),
    ("orders", "order_id", "order_reviews", "order_id"), ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "product_id", "products", "product_id"), ("order_items", "seller_id", "sellers", "seller_id"),
    ("products", "product_category_name", "product_category_name_translation", "product_category_name"),
    ("sellers", "seller_zip_code_prefix", "geolocation", "geolocation_zip_code_prefix"),
    ("customers", "customer_zip_code_prefix", "geolocation", "geolocation_zip_code_prefix"),
)


def _candidate_keys(frame: pd.DataFrame) -> list[dict[str, Any]]:
    keys = []
    for column in frame.columns:
        if frame[column].notna().all():
            keys.append({"columns": [column], "unique": bool(frame[column].is_unique)})
    for columns in (("order_id", "order_item_id"), ("order_id", "payment_sequential")):
        if all(column in frame.columns for column in columns):
            keys.append({"columns": list(columns), "unique": not bool(frame.duplicated(list(columns)).any())})
    return keys


def inspect_csv(path: Path, table: str) -> dict[str, Any]:
    frame = pd.read_csv(path, low_memory=False)
    dates: dict[str, Any] = {}
    for column in frame.columns:
        if "date" in column or "timestamp" in column:
            parsed = pd.to_datetime(frame[column], errors="coerce")
            dates[column] = {
                "missing": int(frame[column].isna().sum()),
                "invalid": int(parsed.isna().sum() - frame[column].isna().sum()),
                "minimum": None if parsed.dropna().empty else str(parsed.min()),
                "maximum": None if parsed.dropna().empty else str(parsed.max()),
            }
    foreign_keys = [
        {"columns": [left_key], "target": f"{right_table}.{right_key}"}
        for left_table, left_key, right_table, right_key in RELATIONSHIPS
        if left_table == table
    ]
    return {
        "filename": path.name, "rows": len(frame), "columns": len(frame.columns),
        "column_names": list(frame.columns), "data_types": {c: str(t) for c, t in frame.dtypes.items()},
        "missing_values": {c: int(n) for c, n in frame.isna().sum().items()},
        "duplicate_rows": int(frame.duplicated().sum()),
        "unique_values": {c: int(frame[c].nunique(dropna=True)) for c in frame.columns if c.endswith("_id") or "zip_code_prefix" in c or c in {"order_item_id", "payment_sequential"}},
        "candidate_primary_keys": _candidate_keys(frame), "candidate_foreign_keys": foreign_keys, "date_columns": dates,
    }


def inspect_dataset(data_dir: Path) -> dict[str, Any]:
    discovered = sorted(data_dir.glob("*.csv"))
    reports = {CSV_FILES.get(path.name, path.stem): inspect_csv(path, CSV_FILES.get(path.name, path.stem)) for path in discovered}
    frames = {table: pd.read_csv(data_dir / filename, low_memory=False) for table, filename in CSV_FILES.items() if (data_dir / filename).exists()}
    relationships = []
    for left_table, left_key, right_table, right_key in RELATIONSHIPS:
        if left_table not in frames or right_table not in frames:
            continue
        left, right = frames[left_table], frames[right_table]
        left_values = left[left_key].dropna()
        right_values = right[right_key].dropna()
        matching = int(left_values.isin(set(right_values)).sum())
        relationships.append({
            "left": f"{left_table}.{left_key}", "right": f"{right_table}.{right_key}",
            "matching_rows": matching, "unmatched_rows": len(left_values) - matching,
            "left_unique_values": int(left_values.nunique()), "right_unique_values": int(right_values.nunique()),
            "left_duplicate_rows": int(left.duplicated(left_key).sum()), "right_duplicate_rows": int(right.duplicated(right_key).sum()),
            "cardinality": "one-to-one" if left_values.is_unique and right_values.is_unique else "one-to-many or many-to-many",
        })
    return {"files": reports, "relationships": relationships}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = inspect_dataset(args.data_dir)
    if args.json:
        print(json.dumps(report, indent=2))
        return
    for item in report["files"].values():
        print(f"{item['filename']}: {item['rows']} rows x {item['columns']} columns; duplicates={item['duplicate_rows']}")
        print(f"  columns: {', '.join(item['column_names'])}")
        print(f"  candidate keys: {item['candidate_primary_keys']}")
        print(f"  candidate foreign keys: {item['candidate_foreign_keys']}")
        for column, dates in item["date_columns"].items():
            print(f"  {column}: {dates}")
    print("\nRelationships:")
    for item in report["relationships"]:
        print(f"  {item['left']} -> {item['right']}: {item['matching_rows']} matching, {item['unmatched_rows']} unmatched, {item['cardinality']}")


if __name__ == "__main__":
    main()