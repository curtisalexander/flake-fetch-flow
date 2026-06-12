#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastmcp",
# ]
# ///
"""Pattern C, SQLite playground edition — ONLY metadata returns. No data value
can ever reach the model through this server.

This is snowflake/mcp-servers/mcp_metadata_only.py with sqlite3 standing in
for Snowflake. The agent can validate SQL and learn result shapes while the
implementation makes it impossible for a cell value to enter the context.

Setup:  uv run sqlite/setup_demo_db.py     (guided tour: sqlite/README.md)
Register (or just open this repo — .mcp.json already does it):
    claude mcp add sqlite-metadata-only -- uv run sqlite/mcp-servers/mcp_metadata_only.py
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("sqlite-metadata-only")

FETCH_BATCH = 10_000

DB_PATH = Path(os.environ.get("FFF_SQLITE_DB", Path(__file__).resolve().parents[1] / "demo.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found — create it first: uv run sqlite/setup_demo_db.py")
    return sqlite3.connect(DB_PATH)


@mcp.tool
def run_query_stats(sql: str) -> str:
    """Run a SQL query on the demo SQLite database and return ONLY metadata —
    never any data values: row count, column names, elapsed seconds.

    Use this to validate queries and understand result shapes with a hard
    guarantee that no cell value enters the model's context.
    """
    start = time.monotonic()
    with connect() as conn:
        cur = conn.execute(sql)
        columns = [col[0] for col in cur.description or []]
        row_count = 0
        while batch := cur.fetchmany(FETCH_BATCH):
            row_count += len(batch)  # counted, never returned
    return json.dumps(
        {
            "row_count": row_count,
            "columns": columns,
            "elapsed_seconds": round(time.monotonic() - start, 2),
        }
    )


if __name__ == "__main__":
    print("sqlite-metadata-only: ready (stdio)", file=sys.stderr)
    mcp.run()
