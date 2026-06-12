#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Create sqlite/demo.db — the zero-setup stand-in for the Snowflake demo table.

Builds the same demo_orders table that snowflake/sql/setup_demo_table.sql
creates in a real warehouse: 100,000 synthetic ACME orders. No accounts, no
credentials, no network — just a file. Seeded, so everyone gets the same data.

    uv run sqlite/setup_demo_db.py

Then follow the guided tour in sqlite/README.md.
"""

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "demo.db"
ROW_COUNT = 100_000
REGIONS = ["North", "South", "East", "West"]
PRODUCTS = ["Anvil", "Rocket Skates", "Tornado Seeds", "Earthquake Pills", "Giant Magnet"]


def main() -> None:
    random.seed(42)
    start = datetime.now().replace(microsecond=0)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DROP TABLE IF EXISTS demo_orders")
    conn.execute(
        """CREATE TABLE demo_orders (
               order_id   INTEGER PRIMARY KEY,
               order_ts   TEXT,
               region     TEXT,
               product    TEXT,
               quantity   INTEGER,
               unit_price REAL
           )"""
    )
    conn.executemany(
        "INSERT INTO demo_orders VALUES (?, ?, ?, ?, ?, ?)",
        (
            (
                i,
                (start - timedelta(minutes=i)).isoformat(sep=" "),
                REGIONS[i % 4],
                PRODUCTS[i % 5],
                random.randint(1, 10),
                round(random.uniform(5.0, 500.0), 2),
            )
            for i in range(ROW_COUNT)
        ),
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM demo_orders").fetchone()[0]
    conn.close()
    # Metadata only, even here — old habits make good defaults.
    print(f"created {DB_PATH} — demo_orders: {n} rows x 6 columns")


if __name__ == "__main__":
    main()
