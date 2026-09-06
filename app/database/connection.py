"""Database connection abstraction for the Olist SQLite database.

This module is intentionally decoupled from the API and agent layers so that
the database backend could be swapped later without touching business logic.

Step 0 scope: connection helper only. No CSV loading or schema creation yet
(that is Step 1 work, see database/loader.py).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Read at call time (not import time) so tests can monkeypatch the env var
# without needing to reload this module.
DEFAULT_DATABASE_PATH = "data/olist.db"


def get_database_path() -> str:
    """Return the configured SQLite database path.

    Falls back to DEFAULT_DATABASE_PATH if DATABASE_PATH is not set, which
    keeps local development possible before the .env file is configured.
    """
    return os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection to the configured database path.

    Callers are responsible for the SQL they execute. In later steps, only
    MCP tools will call this — the LLM agent must never execute arbitrary
    SQL directly (see architectural requirement in the project README).
    """
    db_path = get_database_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()
