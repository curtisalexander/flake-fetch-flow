#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
# ]
# ///
"""Pattern F, SQLite playground edition — run a .sql file into a pandas
DataFrame that does NOT dump its contents.

Usage:
    uv run sqlite/scripts/query_to_dataframe.py sqlite/sql/select_star_caution.sql
    uv run sqlite/scripts/query_to_dataframe.py sqlite/sql/select_star_caution.sql --peek 5

The DataFrame lives in this process's memory and dies when the process exits.
stdout carries only the shape and schema. The dial: --peek N prints the first
N rows — one flag, and suddenly data IS flowing to whoever reads stdout.
"""

import argparse
import os
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(os.environ.get("FFF_SQLITE_DB", Path(__file__).resolve().parents[1] / "demo.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found — create it first: uv run sqlite/setup_demo_db.py")
    return sqlite3.connect(DB_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql_file", type=Path, help="path to a .sql file to execute")
    parser.add_argument(
        "--peek",
        type=int,
        default=0,
        metavar="N",
        help="print the first N rows (default 0: no data values are printed)",
    )
    args = parser.parse_args()

    sql = args.sql_file.read_text()
    with connect() as conn:
        df = pd.read_sql_query(sql, conn)

    # Metadata only: shape and schema. No cell values.
    print(f"DataFrame in memory: {df.shape[0]} rows x {df.shape[1]} columns")
    print("schema:")
    for name, dtype in df.dtypes.items():
        print(f"  {name}: {dtype}")

    if args.peek:
        print(f"\n--peek {args.peek}: data values now flow to stdout ↓")
        print(df.head(args.peek).to_string())

    # The DataFrame is yours from here — aggregate, plot, model, export.
    # Nothing else prints unless you print it.


if __name__ == "__main__":
    main()
