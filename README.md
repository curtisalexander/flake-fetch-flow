# flake-fetch-flow ❄️

**How data actually flows between a coding agent and Snowflake — and why the way you wire it up changes everything.**

This is a learning repo. It exists to make one idea stick:

> **The agent is never connected to Snowflake.** The LLM holds a *reference* to a tool — like a pointer in C, or a call slip at a closed-stacks library. Something else (an MCP server, a script) dereferences that pointer: it connects, runs the SQL, and Snowflake does the processing. The only thing the model ever sees is **whatever that tool chooses to return** — and *you* write the tool.

Every tool here demonstrates a different answer to the question *"where do the result rows go?"* — into the model's context, onto disk, into a DataFrame, or nowhere near the LLM at all.

📖 **Read the full illustrated guide:** [`docs/index.html`](docs/index.html) — written for both technical and non-technical audiences, with data-flow diagrams, worked examples, and a decision matrix. (Served via GitHub Pages once published.)

🧪 **Want to *see* it before wiring up Snowflake?** The [`sqlite/` playground](sqlite/README.md) has twin versions of every tool backed by a local SQLite file — zero accounts, zero credentials — plus a guided tour of copy-paste prompts that demonstrates each pattern live with your agent. The data flows are identical; only the database is humbler.

## The patterns at a glance

| | Pattern | Snowflake (the heart) | SQLite twin | Raw rows enter the LLM's context? |
|---|---|---|---|---|
| **A** | MCP tool returns rows | [`snowflake/mcp-servers/mcp_results_in_context.py`](snowflake/mcp-servers/mcp_results_in_context.py) | [twin](sqlite/mcp-servers/mcp_results_in_context.py) | 🔴 Yes — capped at 200 rows |
| **B** | MCP tool writes CSV, returns metadata | [`snowflake/mcp-servers/mcp_results_to_file.py`](snowflake/mcp-servers/mcp_results_to_file.py) | [twin](sqlite/mcp-servers/mcp_results_to_file.py) | 🟢 No — path + shape only |
| **C** | MCP tool returns metadata only | [`snowflake/mcp-servers/mcp_metadata_only.py`](snowflake/mcp-servers/mcp_metadata_only.py) | [twin](sqlite/mcp-servers/mcp_metadata_only.py) | 🟢 Never — by construction |
| **D** | Script prints to console (agent runs it) | [`snowflake/scripts/query_to_console.py`](snowflake/scripts/query_to_console.py) | [twin](sqlite/scripts/query_to_console.py) | 🔴 Yes — stdout *is* context |
| **E** | Script streams to CSV | [`snowflake/scripts/query_to_file.py`](snowflake/scripts/query_to_file.py) | [twin](sqlite/scripts/query_to_file.py) | 🟢 No — one metadata line |
| **F** | Script loads a DataFrame (no dump) | [`snowflake/scripts/query_to_dataframe.py`](snowflake/scripts/query_to_dataframe.py) | [twin](sqlite/scripts/query_to_dataframe.py) | 🟢 No — shape + schema only |
| **G** | *You* run any script in your own terminal | any of the above | any of the above | 🟢 The LLM isn't even in the room |

Note that A and D are the *same data flow* in different clothes, and so are B and E. MCP-vs-script is an ergonomics choice; **what the tool returns/prints is the data-flow choice.** Diff any Snowflake file against its SQLite twin: the database swaps, the flow doesn't.

## Repo map

```
flake-fetch-flow/
├── README.md                ← you are here
├── docs/index.html          ← the illustrated guide (GitHub Pages)
├── .mcp.json                ← registers all 6 MCP servers with Claude Code
├── .env.example             ← Snowflake connection settings template
├── snowflake/               ← ❤️ THE HEART: real connectors, key-pair auth
│   ├── mcp-servers/         ←    Patterns A, B, C (single-file FastMCP servers)
│   ├── scripts/             ←    Patterns D, E, F (single-file CLI scripts)
│   └── sql/                 ←    demo table setup + example queries
├── sqlite/                  ← 🧪 the playground: same patterns, zero setup
│   ├── README.md            ←    guided tour — steps + prompts to run with an agent
│   ├── setup_demo_db.py     ←    builds demo.db (100k rows, seeded)
│   ├── mcp-servers/ scripts/ sql/
└── results/                 ← where the to-file patterns write CSVs (gitignored)
```

Every Python file is **fully self-contained**: dependencies are declared inline ([PEP 723](https://peps.python.org/pep-0723/)) and [`uv`](https://docs.astral.sh/uv/) resolves them on the fly. No virtualenv, no requirements.txt — `uv run <file>` just works.

## Quickstart — SQLite playground (10 minutes, no account)

```bash
uv run sqlite/setup_demo_db.py   # build the demo database
claude                            # approve the sqlite-* MCP servers when asked
```

Then follow the [guided tour](sqlite/README.md): nine copy-paste prompts that walk every pattern, with notes on exactly what to watch entering (or not entering) the model's context.

## Quickstart — Snowflake (the real thing)

### 0. Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- A Snowflake account and a user you can register a key against

### 1. Generate an RSA key pair

Snowflake's key-pair auth uses an RSA key in PKCS#8 format (2048-bit minimum):

```bash
mkdir -p keys && cd keys

# Encrypted private key (recommended — you'll be prompted for a passphrase):
openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes256 -inform PEM -out rsa_key.p8

# ...or unencrypted, for low-stakes sandboxes:
# openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt

# Derive the public key:
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

The `keys/` directory is gitignored. Keep it that way.

### 2. Register the public key with your Snowflake user

In Snowsight, as a role that can alter the user (paste the key body *without* the `-----BEGIN/END PUBLIC KEY-----` lines):

```sql
ALTER USER my_user SET RSA_PUBLIC_KEY='MIIBIjANBgkqh...';
DESC USER my_user;  -- confirm RSA_PUBLIC_KEY_FP is set
```

> **Tip:** create a dedicated, **read-only role** for agent-driven access. The tools in this repo will happily run whatever SQL they're given; the role is what bounds the blast radius.

### 3. Set environment variables

```bash
cp .env.example .env   # then edit — or export the variables in your shell profile
```

All the Snowflake tools read the same `SNOWFLAKE_*` variables; credentials never appear in code, in `.mcp.json`, or (importantly) in the model's context.

### 4. Create the demo table

```bash
uv run snowflake/scripts/query_to_console.py snowflake/sql/setup_demo_table.sql
```

This builds `demo_orders`: 100,000 synthetic ACME orders — deliberately too big to dump into an LLM.

### 5. Try the flows

```bash
# Pattern D — rows to your console (run by YOU, the LLM sees nothing):
uv run snowflake/scripts/query_to_console.py snowflake/sql/revenue_by_region.sql

# Pattern E — 100k rows to a CSV, one metadata line to stdout:
uv run snowflake/scripts/query_to_file.py snowflake/sql/select_star_caution.sql

# Pattern F — 100k rows into a DataFrame, only shape/schema printed:
uv run snowflake/scripts/query_to_dataframe.py snowflake/sql/select_star_caution.sql
uv run snowflake/scripts/query_to_dataframe.py snowflake/sql/select_star_caution.sql --peek 5  # the dial
```

### 6. Connect the MCP servers to your coding agent

If you open this repo in [Claude Code](https://claude.com/claude-code), [`.mcp.json`](.mcp.json) already registers all six servers — three `snowflake-*`, three `sqlite-*` (you'll be asked to approve them). To register one anywhere else:

```bash
claude mcp add snowflake-in-context -- uv run /absolute/path/to/snowflake/mcp-servers/mcp_results_in_context.py
```

Then ask the agent things like:

- *"Use `run_query` to get revenue by region from demo_orders."* → watch small aggregated rows flow into the conversation (Pattern A)
- *"Use `run_query_to_file` to export all of demo_orders."* → watch 100k rows land in `results/` while the conversation only sees a path and a row count (Pattern B)
- *"Use `run_query_stats` to check how many orders the North region has."* → the model gets a count, never a row (Pattern C)

Any MCP-compatible agent works the same way — the config format barely differs.

## The one-paragraph mental model

When you ask a coding agent to "query Snowflake," the LLM emits a *request to call a tool* — a blob of JSON, nothing more. The agent harness on your machine routes that JSON to an MCP server (or runs a script) **as a separate local process**. That process holds the credentials, opens the TLS connection, and sends the SQL. Snowflake — not the model, not your laptop — scans the 100,000 rows and computes the answer. Rows come back to the local process, which then makes the single most consequential decision in this whole architecture: **what to pass back**. Whatever it returns becomes part of the conversation, and with a remote inference provider, the entire conversation is sent to that provider on every subsequent request. Whatever it *doesn't* return — files on disk, DataFrames in memory — stays home.

For the analogies (pointers, library call slips), the diagrams, the local-LLM case, and why dumping a million rows into a context window makes models *worse*, read [the guide](docs/index.html).

## Publishing this repo

1. `gh repo create flake-fetch-flow --public --source . --push`
2. On GitHub: **Settings → Pages → Source: Deploy from a branch → `main` / `docs/`**
3. The guide goes live at `https://<your-username>.github.io/flake-fetch-flow/`

## A note on safety

These are *teaching* tools, kept intentionally small. Before pointing an agent at data you care about: use a read-only role and a dedicated warehouse, keep keys out of the repo (the `.gitignore` helps), and remember that Snowflake's `QUERY_HISTORY` gives you a complete audit trail of everything the tools ran. The guide's [decision matrix](docs/index.html#matrix) maps data sensitivity to patterns.
