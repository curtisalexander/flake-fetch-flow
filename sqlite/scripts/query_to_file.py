#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Pattern E, SQLite playground edition — run a .sql file and stream the
results to a CSV.

Usage:
    uv run sqlite/scripts/query_to_file.py sqlite/sql/select_star_caution.sql
    uv run sqlite/scripts/query_to_file.py sqlite/sql/revenue_by_region.sql -o results/regions.csv

stdout carries ONE line of metadata. Even when a coding agent runs this, the
raw rows land on disk — not in the model's context.
"""

import argparse
import csv
import os
import sqlite3
import time
from pathlib import Path

FETCH_BATCH = 10_000

DB_PATH = Path(os.environ.get("FFF_SQLITE_DB", Path(__file__).resolve().parents[1] / "demo.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found — create it first: uv run sqlite/setup_demo_db.py")
    return sqlite3.connect(DB_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql_file", type=Path, help="path to a .sql file to execute")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output CSV path (default: results/<sql_name>_<timestamp>.csv)",
    )
    args = parser.parse_args()

    sql = args.sql_file.read_text()
    with connect() as conn:
        cur = conn.execute(sql)
        columns = [col[0] for col in cur.description or []]
        out_path = args.output or Path(
            os.environ.get("FFF_RESULTS_DIR", "results")
        ) / f"{args.sql_file.stem}_{int(time.time())}.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rows_written = 0
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            while batch := cur.fetchmany(FETCH_BATCH):
                writer.writerows(batch)
                rows_written += len(batch)
        # The only thing on stdout — and therefore the only thing an agent's
        # context ever receives — is this one metadata line.
        print(f"wrote {rows_written} rows x {len(columns)} columns to {out_path}")


if __name__ == "__main__":
    main()
