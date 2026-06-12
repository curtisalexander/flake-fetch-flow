#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastmcp",
# ]
# ///
"""Pattern B, SQLite playground edition — query results go to DISK; only
metadata returns to the model.

This is snowflake/mcp-servers/mcp_results_to_file.py with sqlite3 standing in
for Snowflake. The raw rows short-circuit to a local CSV and never enter the
model's context; the model learns only the file's location and shape.

Setup:  uv run sqlite/setup_demo_db.py     (guided tour: sqlite/README.md)
Register (or just open this repo — .mcp.json already does it):
    claude mcp add sqlite-to-file -- uv run sqlite/mcp-servers/mcp_results_to_file.py
"""

import csv
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("sqlite-to-file")

FETCH_BATCH = 10_000

DB_PATH = Path(os.environ.get("FFF_SQLITE_DB", Path(__file__).resolve().parents[1] / "demo.db"))


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found — create it first: uv run sqlite/setup_demo_db.py")
    return sqlite3.connect(DB_PATH)


def results_dir() -> Path:
    d = Path(os.environ.get("FFF_RESULTS_DIR", Path(__file__).resolve().parents[2] / "results"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@mcp.tool
def run_query_to_file(sql: str, filename: str = "") -> str:
    """Run a SQL query on the demo SQLite database and stream the FULL result
    set to a CSV file on local disk. Result size doesn't matter — rows are
    streamed in batches, not held in memory.

    Returns ONLY metadata: file path, row count, and column names. The raw
    rows never enter the model's context.
    """
    with connect() as conn:
        cur = conn.execute(sql)
        columns = [col[0] for col in cur.description or []]
        # Path(...).name strips any directories the caller sneaks in.
        name = Path(filename).name if filename else f"query_{int(time.time())}.csv"
        out_path = results_dir() / name
        rows_written = 0
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            while batch := cur.fetchmany(FETCH_BATCH):
                writer.writerows(batch)
                rows_written += len(batch)
    # Only this small metadata payload crosses back into the model's context.
    return json.dumps({"file": str(out_path), "rows_written": rows_written, "columns": columns})


if __name__ == "__main__":
    print("sqlite-to-file: ready (stdio)", file=sys.stderr)
    mcp.run()
