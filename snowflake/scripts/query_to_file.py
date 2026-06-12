#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "cryptography",
#     "python-dotenv",
#     "snowflake-connector-python",
# ]
# ///
"""Pattern E — run a .sql file on Snowflake and stream the results to a CSV.

Usage:
    uv run snowflake/scripts/query_to_file.py snowflake/sql/select_star_caution.sql
    uv run snowflake/scripts/query_to_file.py snowflake/sql/revenue_by_region.sql -o results/regions.csv

Data flow:
    this script ──SQL──▶ Snowflake ──rows (batched)──▶ results/<file>.csv

stdout carries ONE line of metadata (path, shape, query id). Even when a
coding agent runs this script, the raw rows land on disk — not in the
model's context. The agent only learns where the file is and how big it is.
Result size is a non-issue: rows are streamed in batches, never held in
memory. Open the CSV in Excel, load it in pandas, or hand the path to the
next tool in your pipeline.
"""

import argparse
import csv
import os
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

# Pick up the repo-root .env if present; variables already exported win.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql_file", type=Path, help="path to a .sql file to execute")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="output CSV path (default: results/<sql_name>_<query_id>.csv)",
    )
    args = parser.parse_args()

    sql = args.sql_file.read_text()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        columns = [col[0] for col in cur.description or []]
        out_path = args.output or Path(
            os.environ.get("FFF_RESULTS_DIR", "results")
        ) / f"{args.sql_file.stem}_{cur.sfqid}.csv"
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
        print(f"wrote {rows_written} rows x {len(columns)} columns to {out_path} (query id {cur.sfqid})")


if __name__ == "__main__":
    main()
