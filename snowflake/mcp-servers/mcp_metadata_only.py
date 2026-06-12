#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "cryptography",
#     "fastmcp",
#     "python-dotenv",
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
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv
from fastmcp import FastMCP

# Pick up the repo-root .env if present; variables already exported win.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

try:
    from snowflake.connector.constants import FIELD_ID_TO_NAME
except ImportError:  # type-code names are a nicety, not a requirement
    FIELD_ID_TO_NAME = {}

mcp = FastMCP("snowflake-metadata-only")

FETCH_BATCH = 10_000


def private_key_der() -> bytes:
    """Decode the PEM in $SNOWFLAKE_PRIVATE_KEY into the DER bytes the connector wants.

    The connector's `private_key` parameter doesn't accept PEM text — it
    expects an unencrypted, DER-encoded PKCS#8 blob. So: parse the PEM with
    the `cryptography` library (decrypting it here if a passphrase is set),
    then re-serialize. The key material never leaves this process.
    """
    # The PEM may arrive single-line with literal "\n" sequences (common in
    # .env files) — restore real newlines so it parses either way.
    pem = os.environ["SNOWFLAKE_PRIVATE_KEY"].strip().replace("\\n", "\n")
    passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = serialization.load_pem_private_key(
        pem.encode(), password=passphrase.encode() if passphrase else None
    )
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connect() -> snowflake.connector.SnowflakeConnection:
    """Key-pair (JWT) connection; every setting — the key included — comes from environment variables."""
    missing = [v for v in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY") if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            f"missing environment variables: {', '.join(missing)} — "
            "copy .env.example, fill it in, and export it (see the repo README)"
        )
    params = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "authenticator": "SNOWFLAKE_JWT",
        "private_key": private_key_der(),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE"),
        "database": os.environ.get("SNOWFLAKE_DATABASE"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA"),
        "role": os.environ.get("SNOWFLAKE_ROLE"),
        # Governance freebie: every query lands in QUERY_HISTORY with this
        # tag, so auditing agent activity is a one-line WHERE clause.
        "session_parameters": {"QUERY_TAG": "flake-fetch-flow"},
    }
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
