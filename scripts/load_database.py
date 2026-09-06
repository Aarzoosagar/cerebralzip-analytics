"""Command-line entry point for explicit Olist database initialization."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.database.loader import load_olist_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    load_olist_dataset(args.data_dir)


if __name__ == "__main__":
    main()