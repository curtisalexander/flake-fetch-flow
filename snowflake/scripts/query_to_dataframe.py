#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "snowflake-connector-python[pandas]",
# ]
# ///
"""Pattern F — run a .sql file on Snowflake into a pandas DataFrame that does
NOT dump its contents.

Usage:
    uv run snowflake/scripts/query_to_dataframe.py snowflake/sql/select_star_caution.sql
    uv run snowflake/scripts/query_to_dataframe.py snowflake/sql/select_star_caution.sql --peek 5

Data flow:
    this script ──SQL──▶ Snowflake ──Arrow batches──▶ pandas DataFrame (RAM)

The DataFrame lives in this process's memory and dies when the process
exits. stdout carries only the shape and schema — so even when an agent runs
this, the model learns "100000 rows x 6 columns" and nothing else.

The dial: --peek N prints the first N rows. One flag, and suddenly data IS
flowing into whoever reads stdout. Implementation choices are data-flow
choices — that's the whole lesson of this repo.

In real use you'd extend main(): compute aggregates, build charts, train a
model, write a parquet — the analysis happens HERE, not in the LLM.
"""

import argparse
import os
from pathlib import Path

import snowflake.connector


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql_file", type=Path, help="path to a .sql file to execute")
    parser.add_argument(
        "--peek",
        type=int,
        default=0,
        metavar="N",
        help="print the first N rows (default 0: no data values are printed)",
    )
    args = parser.parse_args()

    sql = args.sql_file.read_text()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql)
        # Arrow-based fetch: Snowflake streams Arrow batches, converted
        # straight into a DataFrame — far faster than fetchall() + construct.
        df = cur.fetch_pandas_all()

    # Metadata only: shape and schema. No cell values.
    print(f"DataFrame in memory: {df.shape[0]} rows x {df.shape[1]} columns")
    print("schema:")
    for name, dtype in df.dtypes.items():
        print(f"  {name}: {dtype}")

    if args.peek:
        print(f"\n--peek {args.peek}: data values now flow to stdout ↓")
        print(df.head(args.peek).to_string())

    # The DataFrame is yours from here — aggregate, plot, model, export.
    # Nothing else prints unless you print it.


if __name__ == "__main__":
    main()
