#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
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
