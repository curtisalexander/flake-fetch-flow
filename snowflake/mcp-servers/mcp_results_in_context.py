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
"""Pattern A — MCP server whose query results flow INTO the model's context.

Data flow when a coding agent uses this server:

    LLM ──"call run_query(sql)"──▶ agent harness ──JSON-RPC over stdio──▶ this server
    this server ──SQL over TLS──▶ Snowflake (data is processed THERE)
    this server ◀──result rows─── Snowflake
    agent harness ◀──JSON-RPC tool result (rows as JSON)─── this server
    └─▶ the harness injects that JSON into the conversation as a tool result,
        so EVERY VALUE returned here becomes part of the model's context —
        and, with a remote inference provider, leaves your machine on the
        very next request.

Use this pattern for small, filtered, or aggregated results the model should
reason about directly. The row cap is the safety rail; the real control is
writing SQL that aggregates/filters server-side.

Register with Claude Code (run from the repo root):
    claude mcp add snowflake-in-context -- uv run snowflake/mcp-servers/mcp_results_in_context.py
(or just open this repo — .mcp.json already registers it project-wide)
"""

import json
import os
import sys
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv
from fastmcp import FastMCP

# Pick up the repo-root .env if present; variables already exported win.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

mcp = FastMCP("snowflake-in-context")

# No single tool call may push more rows than this into the model's context.
HARD_ROW_CAP = 200


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
def run_query(sql: str, max_rows: int = 50) -> str:
    """Run a SQL query on Snowflake and return the result rows directly.

    The rows come back as JSON and are placed straight into the model's
    context. Keep results small: aggregate, filter, and LIMIT in SQL so
    Snowflake does the heavy lifting. max_rows is clamped to 200.
    """
    max_rows = max(1, min(max_rows, HARD_ROW_CAP))
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [col[0] for col in cur.description or []]
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        payload = {
            "columns": columns,
            "rows": rows[:max_rows],
            "rows_returned": min(len(rows), max_rows),
            "truncated": truncated,
            "query_id": cur.sfqid,
        }
    # This string is the tool result: it travels back over stdio and is
    # injected into the conversation. This line IS the context boundary.
    return json.dumps(payload, default=str)


if __name__ == "__main__":
    # stdout belongs to the JSON-RPC protocol in a stdio server — log to stderr.
    print("snowflake-in-context: ready (stdio)", file=sys.stderr)
    mcp.run()
