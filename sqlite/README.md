# The SQLite playground 🧪

**Watch every data-flow pattern happen, live, in about ten minutes — no Snowflake account required.**

This directory is a *supplement*. The heart of this repo is [`snowflake/`](../snowflake/) — the real connectors, real key-pair auth, real warehouse. But the lesson of this repo is about **where the rows go**, and that lesson is identical whether the database is a cloud warehouse or a local file. So: every tool in `snowflake/` has a twin here with `sqlite3` standing in. Diff any pair of files — the connection code shrinks, the data flow doesn't change.

> **The one honest difference:** with Snowflake, "the database does the heavy lifting" means a remote warehouse you pay for; here it means your laptop. Every arrow that matters — what enters the model's context, what lands on disk, what stays in memory — is the same.

## Setup (two steps)

1. **Build the demo database** (100,000 synthetic orders, seeded so everyone gets the same data):

   ```bash
   uv run sqlite/setup_demo_db.py
   ```

   (Need `uv`? `curl -LsSf https://astral.sh/uv/install.sh | sh`)

2. **Start your coding agent in the repo root.** If that's [Claude Code](https://claude.com/claude-code), just run `claude` — the repo's [`.mcp.json`](../.mcp.json) registers the `sqlite-*` MCP servers and it will ask you to approve them. Other MCP-capable agents: register `sqlite/mcp-servers/*.py` per their docs.

That's it. No credentials, no network, no cleanup beyond deleting `demo.db`.

## The guided tour

Paste each prompt into your agent, then — this is the important part — **watch the conversation, not just the answer.** The whole point is noticing *what entered the model's context* at each step. (Pattern letters match the [main guide](../docs/index.html) and the [decision matrix](../docs/index.html#matrix).)

### 1 · Pattern A — small results into context (the happy path) 🔴

> Use the sqlite-in-context run_query tool to show me revenue by region from demo_orders.

**Watch for:** the tool result in the conversation contains the actual rows as JSON — 4 rows, ~60 tokens. That data is now part of the model's context for the rest of the chat. For an aggregate this small, that's exactly what you want.

### 2 · Pattern A — the firehose attempt (the guard rail) 🔴

> Use run_query to fetch every row of demo_orders.

**Watch for:** the tool returns at most 200 rows and `"truncated": true`. The cap lives in *the server code you control* — open `sqlite/mcp-servers/mcp_results_in_context.py` and find `HARD_ROW_CAP`. The model didn't decide this; your implementation did.

### 3 · Pattern B — big results to disk, metadata to context 🟢🟠

> Use run_query_to_file to export all of demo_orders.

**Watch for:** a ~100,000-row CSV appears in `results/`, but the conversation only shows a path, a row count, and column names. One hundred thousand rows moved; roughly thirty tokens entered the context.

### 4 · The escape hatch (the honesty box, live) 🔴

> Now show me the first 5 lines of that CSV.

**Watch for:** the agent reads the file (probably with `head` or its file tool) — and *now* those 5 rows are in context. The file boundary kept data out **by default**, not by padlock. Note that this happened as a separate, visible, permission-gated action — that's the actual guarantee.

### 5 · Pattern C — metadata only, by construction 🟢

> Use run_query_stats to tell me the shape of SELECT * FROM demo_orders.

**Watch for:** row count, column names, timing — and no way to get more. Read `sqlite/mcp-servers/mcp_metadata_only.py`: rows are counted and discarded. An agent could iterate on SQL against sensitive data all day through this tool without one cell value reaching the model.

### 6 · Pattern D — the sleeper: a script that prints 🔴

> Run `uv run sqlite/scripts/query_to_console.py sqlite/sql/revenue_by_region.sql` and interpret the output.

**Watch for:** no MCP anywhere — just the shell tool — yet the printed rows are in the model's context all the same. **stdout is context.** Now imagine that command with `sqlite/sql/select_star_caution.sql` and no `--max-rows`: a 100k-row firehose with no cap. (Try `--max-rows 20` if you want a taste.)

### 7 · Pattern E — the same script idea, pointed at a file 🟢🟠

> Run `uv run sqlite/scripts/query_to_file.py sqlite/sql/select_star_caution.sql` and tell me what happened.

**Watch for:** one metadata line in the conversation; 100,000 rows on disk. Patterns D and E are near-identical scripts — compare them — differing only in where the rows go. *Implementation choices are data-flow choices.*

### 8 · Pattern F — DataFrame in memory, and the one-flag dial 🟢→🔴

> Run `uv run sqlite/scripts/query_to_dataframe.py sqlite/sql/select_star_caution.sql` and report what it says.

**Watch for:** "100000 rows x 6 columns" plus a schema — the data lived in pandas, in RAM, and died with the process. Then run the dial:

> Run it again with `--peek 5`.

Five rows of data in context. The distance between 🟢 and 🔴 was one `print(df.head())`.

### 9 · Pattern G — the LLM leaves the room 🟢

In a **separate terminal** (not through the agent), run:

```bash
uv run sqlite/scripts/query_to_console.py sqlite/sql/revenue_by_region.sql
```

Same script as step 6, same output — but the model never saw any of it, because nothing routed stdout into a conversation. Who runs the tool is part of the data flow.

## What you just saw

| Step | Pattern | Rows in model context? |
|---|---|---|
| 1, 2 | A — MCP returns rows | 🔴 yes, capped |
| 3 | B — MCP writes file | 🟢 disk · 🟠 metadata |
| 4 | escape hatch | 🔴 by separate visible action |
| 5 | C — metadata only | 🟢 never, by construction |
| 6 | D — script prints, agent runs | 🔴 yes, uncapped |
| 7 | E — script writes file | 🟢 disk · 🟠 one line |
| 8 | F — DataFrame | 🟢 RAM (until `--peek`) |
| 9 | G — human runs it | 🟢 LLM not in the loop |

Same database, same SQL, nine different answers to "what did the AI see?" — every one of them decided by implementation, not by the model.

**Now go read how this works against the real thing** — key-pair auth, warehouses, Arrow, `QUERY_HISTORY` — in [`snowflake/`](../snowflake/) and the [illustrated guide](../docs/index.html).
