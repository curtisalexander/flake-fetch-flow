#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastmcp",
#     "snowflake-connector-python",
# ]
# ///
"""Pattern B — MCP server that writes query results to DISK; only metadata
returns to the model.

Data flow when a coding agent uses this server:

    LLM ──"call run_query_to_file(sql)"──▶ agent harness ──stdio──▶ this server
    this server ──SQL──▶ Snowflake ──rows──▶ this server ──▶ results/<file>.csv
    agent harness ◀──{path, row_count, columns} ONLY─── this server

The raw rows short-circuit to a local CSV and NEVER enter the model's
context. The model learns the file's location and shape, and can then
decide (or be told) what to do next: hand the path to you, load it in a
script, or peek at a few rows with another tool.

Honest caveat: this keeps data out of context BY DEFAULT, not by guarantee —
an agent with shell access could still `head` the file. The point is that
nothing flows to the model unless a separate, visible action reads it.

Register with Claude Code (run from the repo root):
    claude mcp add snowflake-to-file -- uv run snowflake/mcp-servers/mcp_results_to_file.py
"""

import csv
import json
import os
import sys
from pathlib import Path

import snowflake.connector
from fastmcp import FastMCP

mcp = FastMCP("snowflake-to-file")

FETCH_BATCH = 10_000


def connect() -> snowflake.connector.SnowflakeConnection:
    """Key-pair (JWT) connection; every setting comes from environment variables."""
    missing = [v for v in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_FILE") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"missing environment variables: {', '.join(missing)} — "
            "copy .env.example, fill it in, and export it (see the repo README)"
        )
    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "authenticator": "SNOWFLAKE_JWT",
        "private_key_file": os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"],
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE"),
        "database": os.environ.get("SNOWFLAKE_DATABASE"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA"),
        "role": os.environ.get("SNOWFLAKE_ROLE"),
        # Governance freebie: every query lands in QUERY_HISTORY with this
        # tag, so auditing agent activity is a one-line WHERE clause.
        "session_parameters": {"QUERY_TAG": "flake-fetch-flow"},
    }
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    if passphrase:
        params["private_key_file_pwd"] = passphrase
    return snowflake.connector.connect(**{k: v for k, v in params.items() if v})


def results_dir() -> Path:
    d = Path(os.environ.get("FFF_RESULTS_DIR", Path(__file__).resolve().parents[2] / "results"))
    d.mkdir(parents=True, exist_ok=True)
    return d


@mcp.tool
def run_query_to_file(sql: str, filename: str = "") -> str:
    """Run a SQL query on Snowflake and stream the FULL result set to a CSV
    file on local disk. Result size doesn't matter — rows are streamed in
    batches, not held in memory.

    Returns ONLY metadata: file path, row count, and column names. The raw
    rows never enter the model's context.
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [col[0] for col in cur.description or []]
        # Path(...).name strips any directories the caller sneaks in.
        name = Path(filename).name if filename else f"query_{cur.sfqid}.csv"
        out_path = results_dir() / name
        rows_written = 0
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            while batch := cur.fetchmany(FETCH_BATCH):
                writer.writerows(batch)
                rows_written += len(batch)
        query_id = cur.sfqid
    # Only this small metadata payload crosses back into the model's context.
    return json.dumps(
        {
            "file": str(out_path),
            "rows_written": rows_written,
            "columns": columns,
            "query_id": query_id,
        }
    )


if __name__ == "__main__":
    print("snowflake-to-file: ready (stdio)", file=sys.stderr)
    mcp.run()
