#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "snowflake-connector-python",
# ]
# ///
"""Pattern D — run a .sql file on Snowflake and print every row to the console.

Usage:
    uv run snowflake/scripts/query_to_console.py snowflake/sql/revenue_by_region.sql
    uv run snowflake/scripts/query_to_console.py snowflake/sql/select_star_caution.sql --max-rows 20

Data flow:
    this script ──SQL──▶ Snowflake ──rows──▶ this script ──▶ stdout

The catch: WHO is reading stdout?
  * You, in a terminal: the data stops at your screen. The LLM never sees it.
  * A coding agent, via its shell tool: stdout is captured and injected into
    the model's context — the same exposure as an MCP tool that returns rows
    (Pattern A), just without any row cap unless you pass --max-rows.

Same script, two completely different data flows. That's the point.
"""

import argparse
import os
import sys
from pathlib import Path

import snowflake.connector


def connect() -> snowflake.connector.SnowflakeConnection:
    """Key-pair (JWT) connection; every setting comes from environment variables."""
    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "authenticator": "SNOWFLAKE_JWT",
        "private_key_file": os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"],
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE"),
        "database": os.environ.get("SNOWFLAKE_DATABASE"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA"),
        "role": os.environ.get("SNOWFLAKE_ROLE"),
    }
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    if passphrase:
        params["private_key_file_pwd"] = passphrase
    return snowflake.connector.connect(**{k: v for k, v in params.items() if v})


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
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [col[0] for col in cur.description or []]
        rows = cur.fetchmany(args.max_rows) if args.max_rows else cur.fetchall()
        # Everything printed below goes to stdout. If an agent ran this
        # command, all of it lands in the model's context.
        print_table(columns, rows)
        print(f"\n({len(rows)} rows, query id {cur.sfqid})", file=sys.stderr)


if __name__ == "__main__":
    main()
