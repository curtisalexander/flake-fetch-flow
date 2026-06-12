# snowflake/ — the heart of this repo ❤️❄️

These are the real connectors: the [Snowflake Connector for Python](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector) with key-pair (JWT) authentication, configured entirely through `SNOWFLAKE_*` environment variables.

- **`mcp-servers/`** — Patterns A, B, C: three single-file FastMCP servers that differ only in *what they return to the model* (rows / file path / metadata).
- **`scripts/`** — Patterns D, E, F: three single-file CLI scripts that differ only in *where the rows go* (stdout / CSV / DataFrame).
- **`sql/`** — demo table setup (100k synthetic orders) and example queries.

Setup — key generation, `ALTER USER ... SET RSA_PUBLIC_KEY`, env vars, demo table — is in the [root README](../README.md#quickstart--snowflake-the-real-thing). The concepts are in the [illustrated guide](../docs/index.html).

No Snowflake account handy? Every file here has a zero-setup twin in [`../sqlite/`](../sqlite/README.md) — same data flows, local database, guided tour included. Diff the twins; the flow survives the database swap. That's the lesson.
