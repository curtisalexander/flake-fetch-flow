#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Manual smoke test — run me after cloning or changing anything.

    uv run smoke_test.py

One file, no framework, stdlib only. Exercises the entire zero-credential
surface of the repo: the setup script, all three SQLite scripts (Patterns
D, E, F), and all three SQLite MCP servers over real JSON-RPC stdio
(Patterns A, B, C — including the firehose cap). Prints one line per check;
exits nonzero if anything fails.

The Snowflake twins share the same structure but need real credentials, so
they aren't covered here — the closest proxy is that the SQLite twins pass.
"""

import json
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECKS: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append(ok)
    print(f"{'✓' if ok else '✗ FAIL:'} {name}" + (f"\n    {detail}" if detail and not ok else ""))


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", *args], cwd=ROOT, capture_output=True, text=True, timeout=300
    )


def mcp_call(server: str, tool: str, arguments: dict) -> dict:
    """Speak minimal MCP to a stdio server: initialize → initialized → tools/call."""
    proc = subprocess.Popen(
        ["uv", "run", server],
        cwd=ROOT,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv(want_id: int) -> dict:
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(f"{server} closed stdout before responding")
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue  # ignore any non-JSON noise
            if msg.get("id") == want_id:
                return msg

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke-test", "version": "0"},
                },
            }
        )
        recv(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
        resp = recv(2)
        return json.loads(resp["result"]["content"][0]["text"])
    finally:
        proc.kill()


def main() -> None:
    signal.alarm(900)  # global watchdog: no hung server can wedge the test

    # -- setup ------------------------------------------------------------
    r = run("sqlite/setup_demo_db.py")
    check(
        "setup_demo_db builds 100,000 seeded rows",
        r.returncode == 0 and "100000 rows" in r.stdout,
        r.stderr.strip()[-300:],
    )

    # -- Pattern D: script prints rows to stdout --------------------------
    r = run("sqlite/scripts/query_to_console.py", "sqlite/sql/revenue_by_region.sql")
    check(
        "query_to_console prints all 4 regions",
        r.returncode == 0 and all(reg in r.stdout for reg in ("North", "South", "East", "West")),
        (r.stdout + r.stderr).strip()[-300:],
    )

    # -- Pattern E: script streams rows to CSV, one metadata line ---------
    out = ROOT / "results" / "smoke_test.csv"
    r = run("sqlite/scripts/query_to_file.py", "sqlite/sql/select_star_caution.sql", "-o", str(out))
    lines = sum(1 for _ in open(out)) if out.exists() else 0
    check(
        "query_to_file writes header + 100,000 rows",
        r.returncode == 0 and lines == 100_001,
        f"returncode={r.returncode}, lines={lines}",
    )
    check(
        "query_to_file stdout is a single metadata line",
        r.returncode == 0 and len(r.stdout.strip().splitlines()) == 1,
        r.stdout.strip()[-300:],
    )

    # -- Pattern F: DataFrame, shape only ----------------------------------
    r = run("sqlite/scripts/query_to_dataframe.py", "sqlite/sql/select_star_caution.sql")
    check(
        "query_to_dataframe reports shape, leaks no values",
        r.returncode == 0 and "100000 rows x 6 columns" in r.stdout and "Anvil" not in r.stdout,
        (r.stdout + r.stderr).strip()[-300:],
    )

    # -- Pattern A: MCP returns rows in-context, with a cap ----------------
    payload = mcp_call(
        "sqlite/mcp-servers/mcp_results_in_context.py",
        "run_query",
        {"sql": "SELECT region, COUNT(*) AS orders FROM demo_orders GROUP BY region"},
    )
    check(
        "MCP run_query returns 4 aggregated rows",
        payload.get("rows_returned") == 4 and payload.get("truncated") is False,
        json.dumps(payload)[:300],
    )
    payload = mcp_call(
        "sqlite/mcp-servers/mcp_results_in_context.py",
        "run_query",
        {"sql": "SELECT * FROM demo_orders", "max_rows": 100_000},
    )
    check(
        "MCP run_query caps the firehose at 200 rows",
        payload.get("rows_returned") == 200 and payload.get("truncated") is True,
        json.dumps({k: v for k, v in payload.items() if k != "rows"})[:300],
    )

    # -- Pattern B: MCP writes file, returns metadata only -----------------
    payload = mcp_call(
        "sqlite/mcp-servers/mcp_results_to_file.py",
        "run_query_to_file",
        {"sql": "SELECT * FROM demo_orders", "filename": "smoke_test_mcp.csv"},
    )
    mcp_csv = Path(payload.get("file", "/nonexistent"))
    check(
        "MCP run_query_to_file writes 100k rows, returns only metadata",
        payload.get("rows_written") == 100_000 and mcp_csv.exists() and "rows" not in payload,
        json.dumps(payload)[:300],
    )

    # -- Pattern C: MCP metadata only ---------------------------------------
    payload = mcp_call(
        "sqlite/mcp-servers/mcp_metadata_only.py",
        "run_query_stats",
        {"sql": "SELECT * FROM demo_orders"},
    )
    check(
        "MCP run_query_stats returns count + columns, no values",
        payload.get("row_count") == 100_000
        and payload.get("columns") == ["order_id", "order_ts", "region", "product", "quantity", "unit_price"]
        and "rows" not in payload,
        json.dumps(payload)[:300],
    )

    # -- cleanup ------------------------------------------------------------
    out.unlink(missing_ok=True)
    if mcp_csv != Path("/nonexistent"):
        mcp_csv.unlink(missing_ok=True)

    passed = sum(CHECKS)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    sys.exit(0 if passed == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
