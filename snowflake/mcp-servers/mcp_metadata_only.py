#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastmcp",
#     "snowflake-connector-python",
# ]
# ///
"""Pattern C — MCP server that returns ONLY metadata. No data value can ever
reach the model through this server.

Data flow when a coding agent uses this server:

    LLM ──"call run_query_stats(sql)"──▶ agent harness ──stdio──▶ this server
    this server ──SQL──▶ Snowflake ──rows──▶ this server (counted, discarded)
    agent harness ◀──{row_count, column names/types, timing}─── this server

The strictest pattern: the agent can validate SQL, learn result shapes, and
iterate on queries — while the implementation makes it impossible for a cell
value to flow into the model's context (and therefore impossible for one to
reach a remote inference provider via this tool).

Register with Claude Code (run from the repo root):
    claude mcp add snowflake-metadata-only -- uv run snowflake/mcp-servers/mcp_metadata_only.py
"""

import json
import os
import sys
import time

import snowflake.connector
from fastmcp import FastMCP

try:
    from snowflake.connector.constants import FIELD_ID_TO_NAME
except ImportError:  # type-code names are a nicety, not a requirement
    FIELD_ID_TO_NAME = {}

mcp = FastMCP("snowflake-metadata-only")

FETCH_BATCH = 10_000


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


@mcp.tool
def run_query_stats(sql: str) -> str:
    """Run a SQL query on Snowflake and return ONLY metadata — never any data
    values: row count, column names and types, query id, elapsed seconds.

    Use this to validate queries and understand result shapes with a hard
    guarantee that no cell value enters the model's context.
    """
    start = time.monotonic()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [
            {"name": col[0], "type": str(FIELD_ID_TO_NAME.get(col[1], col[1]))}
            for col in cur.description or []
        ]
        row_count = 0
        while batch := cur.fetchmany(FETCH_BATCH):
            row_count += len(batch)  # counted, never returned
        query_id = cur.sfqid
    return json.dumps(
        {
            "row_count": row_count,
            "columns": columns,
            "query_id": query_id,
            "elapsed_seconds": round(time.monotonic() - start, 2),
        }
    )


if __name__ == "__main__":
    print("snowflake-metadata-only: ready (stdio)", file=sys.stderr)
    mcp.run()
