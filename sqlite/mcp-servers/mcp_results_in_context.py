#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastmcp",
# ]
# ///
"""Pattern A, SQLite playground edition — query results flow INTO the model's
context.

This is snowflake/mcp-servers/mcp_results_in_context.py with sqlite3 standing
in for Snowflake so you can watch the data flow with zero setup. Diff the two
files: the database swaps, the connection code shrinks, and THE DATA FLOW IS
IDENTICAL — whatever this tool returns lands in the model's context.

Setup:  uv run sqlite/setup_demo_db.py     (guided tour: sqlite/README.md)
Register (or just open this repo — .mcp.json already does it):
    claude mcp add sqlite-in-context -- uv run sqlite/mcp-servers/mcp_results_in_context.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("sqlite-in-context")

# No single tool call may push more rows than this into the model's context.
HARD_ROW_CAP = 200

DB_PATH = Path(os.environ.get("FFF_SQLITE_DB", Path(__file__).resolve().parents[1] / "demo.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found — create it first: uv run sqlite/setup_demo_db.py")
    return sqlite3.connect(DB_PATH)


@mcp.tool
def run_query(sql: str, max_rows: int = 50) -> str:
    """Run a SQL query on the demo SQLite database and return the result rows
    directly.

    The rows come back as JSON and are placed straight into the model's
    context. Keep results small: aggregate, filter, and LIMIT in SQL so the
    database does the heavy lifting. max_rows is clamped to 200.
    """
    max_rows = max(1, min(max_rows, HARD_ROW_CAP))
    with connect() as conn:
        cur = conn.execute(sql)
        columns = [col[0] for col in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        payload = {
            "columns": columns,
            "rows": rows[:max_rows],
            "rows_returned": min(len(rows), max_rows),
            "truncated": truncated,
        }
    # This string is the tool result: it travels back over stdio and is
    # injected into the conversation. This line IS the context boundary.
    return json.dumps(payload, default=str)


if __name__ == "__main__":
    print("sqlite-in-context: ready (stdio)", file=sys.stderr)
    mcp.run()
