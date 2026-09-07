"""Startup helpers for obtaining the Olist data and initializing SQLite."""

from __future__ import annotations

import os
import sqlite3
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from app.database.connection import get_database_path
from app.database.loader import CSV_FILES, load_olist_dataset
from app.database.models import REQUIRED_TABLES

DEFAULT_DATASET_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce?datasetVersionNumber=2"


def database_initialized() -> bool:
    """Return whether the configured database contains every required table."""
    database_path = Path(get_database_path())
    if not database_path.is_file():
        return False
    try:
        with sqlite3.connect(database_path) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            order_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] if "orders" in tables else 0
        return set(REQUIRED_TABLES).issubset(tables) and order_count > 0
    except sqlite3.DatabaseError:
        return False


def _download_dataset(data_dir: Path) -> None:
    archive_path = data_dir / "brazilian-ecommerce.zip"
    url = os.environ.get("DATASET_URL", DEFAULT_DATASET_URL)
    try:
        urllib.request.urlretrieve(url, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            root = data_dir.resolve()
            for member in archive.infolist():
                target = (data_dir / member.filename).resolve()
                if root not in target.parents and target != root:
                    raise RuntimeError("Dataset archive contains an unsafe path.")
            archive.extractall(data_dir)
    except (OSError, RuntimeError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"Could not obtain the Olist dataset from {url}. Set DATASET_URL to a reachable archive URL and retry.") from exc
    finally:
        archive_path.unlink(missing_ok=True)


def ensure_database(data_dir: str | Path | None = None) -> dict[str, int] | None:
    """Initialize the database once, obtaining CSVs automatically when needed."""
    if database_initialized():
        return None
    root = Path(data_dir or os.environ.get("DATA_DIR", Path(get_database_path()).parent))
    root.mkdir(parents=True, exist_ok=True)
    missing = [filename for filename, _ in CSV_FILES.values() if not (root / filename).is_file()]
    if missing:
        _download_dataset(root)
    try:
        return load_olist_dataset(root)
    except (OSError, ValueError, sqlite3.DatabaseError) as exc:
        raise RuntimeError(f"The Olist dataset could not be loaded from {root}: {exc}") from exc