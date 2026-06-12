#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Pattern D, SQLite playground edition — run a .sql file and print every row
to the console.

Usage:
    uv run sqlite/scripts/query_to_console.py sqlite/sql/revenue_by_region.sql
    uv run sqlite/scripts/query_to_console.py sqlite/sql/select_star_caution.sql --max-rows 20

The catch (same as the Snowflake version): WHO is reading stdout?
  * You, in a terminal: the data stops at your screen. The LLM never sees it.
  * A coding agent, via its shell tool: stdout is captured and injected into
    the model's context — the same exposure as an MCP tool that returns rows.
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(os.environ.get("FFF_SQLITE_DB", Path(__file__).resolve().parents[1] / "demo.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found — create it first: uv run sqlite/setup_demo_db.py")
    return sqlite3.connect(DB_PATH)


def print_table(columns: list[str], rows: list[tuple]) -> None:
    cells = [["" if v is None else str(v) for v in row] for row in rows]
    widths = [len(c) for c in columns]
    for row in cells:
        for i, v in enumerate(row):
            widths[i] = max(widths[i], len(v))
    print(" | ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("-+-".join("-" * w for w in widths))
    for row in cells:
        print(" | ".join(v.ljust(w) for v, w in zip(row, widths)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql_file", type=Path, help="path to a .sql file to execute")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="print at most N rows (default: ALL of them — caveat emptor)",
    )
    args = parser.parse_args()

    sql = args.sql_file.read_text()
    with connect() as conn:
        cur = conn.execute(sql)
        columns = [col[0] for col in cur.description or []]
        rows = cur.fetchmany(args.max_rows) if args.max_rows else cur.fetchall()
        # Everything printed below goes to stdout. If an agent ran this
        # command, all of it lands in the model's context.
        print_table(columns, rows)
        print(f"\n({len(rows)} rows)", file=sys.stderr)


if __name__ == "__main__":
    main()
