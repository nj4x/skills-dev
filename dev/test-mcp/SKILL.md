---
name: test-mcp
description: Test arbitrary local MCP (stdio) servers end-to-end — launch mcp-wrapper as an HTTP proxy, discover tools, invoke user-confirmed non-destructive tools, and analyze results from /tmp/mcp-wrapper.log.
---

# test-mcp

## Prerequisites

This skill requires `mcp-wrapper` to be installed and on PATH. It is a separate tool not included in this repository — install it before using this skill:

```bash
which mcp-wrapper   # verify it is available
```

If `mcp-wrapper` is not found, obtain and install it from its source, then verify `which mcp-wrapper` returns a path before proceeding.

## Overview

This skill drives a black-box test of an arbitrary local MCP (stdio) server. It:

1. Writes a temporary `mcpServers` config for the server under test.
2. Starts `mcp-wrapper` as an HTTP proxy in front of it (127.0.0.1:8005).
3. Discovers every tool the server exposes.
4. **Presents non-destructive tools to the user for confirmation**, then invokes
   only the confirmed set. Mutating tools are never called unless the user
   explicitly names them.
5. Cleans up the proxy and temp files when done.

Full command reference and edge cases live in `docs/workflow.md`. Read it before
running anything non-trivial.

## Critical rules

- **NEVER kill `mcp-wrapper` processes.** Long MCP operations routinely take
  minutes (indexing, downloads, searches). Killing looks like a fix and is not.
- **The proxy runs in the foreground and never exits on its own** — it is a
  uvicorn server. You MUST launch it in the background (`&` or
  `run_in_background: true`), or it will block the session.
- **Suspected timeout? Read `/tmp/mcp-wrapper.log` FIRST**, before any other
  action. The answer is almost always in the log.
- **Poll the log every 40–60 seconds** for long-running calls. Only conclude a
  real timeout when there is **no new log activity for several minutes**.
- **Start the server, wait for readiness, then query.** Do not fire client calls
  before the health endpoint responds.
- Array/object params **must be JSON-encoded** on the CLI.
- **Judge results by exit code, not by a magic field.** Exit code `0` = pass,
  exit code `1` = fail; errors land on stderr. Do not look for `"success": true`
  — CLI output may be JSON, plain text, or mixed depending on the tool.
- **Never auto-invoke mutating tools.** Only call write/delete/destructive tools
  when the user explicitly names them and approves the inputs.

## The 4-phase workflow

### Phase 1 — Create the temp config

Write a config describing the server(s) under test. Use
`/tmp/test-mcp-config.json`. The `command` can be `uvx`, `node`, an absolute
python path, etc. Realistic example (note the disabled server is defined but not
launched):

```json
{
  "mcpServers": {
    "tradingview-mcp": {
      "command": "node",
      "args": ["/Users/roman/projects/pro-trading/vendor/tradingview-mcp/src/server.js"],
      "env": { "TV_MCP_AUTO_LAUNCH": "1" },
      "disabled": false
    },
    "massive-mcp": {
      "command": "/Users/roman/projects/pro-trading/.venv/bin/python",
      "args": ["-m", "protrading.massive_mcp"],
      "env": {},
      "disabled": true
    }
  }
}
```

Simple `uvx` form for a published package:

```json
{
  "mcpServers": {
    "sut": {
      "command": "uvx",
      "args": ["some-package@latest"],
      "env": { "API_KEY": "value" },
      "disabled": false
    }
  }
}
```

Ask the user for `command`, `args`, and any required `env` if not provided. The
server key (e.g. `tradingview-mcp`, `sut`) is used in `--server <name>`, the
health path, and the `[<name>]` log prefix.

### Phase 2 — Start mcp-wrapper (HTTP proxy)

The proxy is a foreground uvicorn process that **never exits on its own**. Launch
it in the background. Mount one server with `--server <name>` (omit to mount all
non-disabled servers):

```bash
# Bash with & (append the ampersand so the shell returns immediately)
mcp-wrapper --config /tmp/test-mcp-config.json --http --server tradingview-mcp &

# In this harness, prefer run_in_background: true on the Bash tool call instead.
```

Poll the health endpoint until it responds (do not proceed until it succeeds):

```bash
curl -s http://127.0.0.1:8005/mcp-wrapper/tradingview-mcp/health
```

Confirm the subprocess came up cleanly:

```bash
tail -n 40 /tmp/mcp-wrapper.log
```

Look for `[<timestamp>] [tradingview-mcp] ...` startup lines with no traceback.

### Phase 3 — Discover and triage tools

`--server <name>` auto-derives the client URL — it is exactly equivalent to
`--url http://127.0.0.1:8005/mcp-wrapper/<name>`. Use whichever you prefer.

```bash
# All mounted servers
curl -s http://127.0.0.1:8005/mcp-wrapper/servers-info

# List this server's tools (names, params, docstrings)
mcp-wrapper --client --server tradingview-mcp --help
```

Classify each tool as **non-destructive** (read/list/search/get/health, or
dry-run defaults) or **mutating** (write/index/create/update/delete/send/purge).

Present both lists to the user and stop:

> **Non-destructive tools (safe to test):**
> - `get_quote` — params: symbol (str)
> - `list_symbols` — no params
>
> **Mutating tools (skipped by default):**
> - `place_order` — writes an order
>
> Which non-destructive tools should I run? I will use minimal valid inputs.
> To test a mutating tool, name it and provide the exact inputs.

Do not infer consent — wait for the reply.

### Phase 4 — Invoke confirmed tools and analyze

Call each user-confirmed tool. Mutating tools are included only if the user named
them explicitly, using exactly the inputs the user supplied.

```bash
# No params
mcp-wrapper --client --server tradingview-mcp --tool list_symbols

# Scalar param
mcp-wrapper --client --server tradingview-mcp --tool get_quote --param:symbol "AAPL"

# Array param (JSON-encoded)
mcp-wrapper --client --server sut --tool index_files --param:paths '["/tmp/sut-test.txt"]'

# Object param (JSON-encoded)
mcp-wrapper --client --server sut --tool configure --param:options '{"recursive":true}'
```

For a non-destructive tool that needs a path param, create a throwaway file first
(`printf 'test\n' > /tmp/sut-test.txt`) and track it for cleanup.

Judge each result:
- **Exit code `0` = pass, exit code `1` = fail.** Check `$?` after the call.
- Output may be JSON, plain text, or mixed — read it as text; don't assume JSON
  or hunt for a `success` field.
- Cross-check `/tmp/mcp-wrapper.log` for matching `[<name>]` lines — a traceback
  or `ERROR` there means the tool failed even if the CLI printed a result.

Summarize per tool: name, input used, exit code, pass/fail, evidence (result
snippet + decisive log lines).

### Cleanup (always runs after tests complete)

```bash
# 1. Stop the proxy you started
pkill -f "mcp-wrapper --config /tmp/test-mcp-config.json"

# 2. Remove the temp config
rm -f /tmp/test-mcp-config.json

# 3. Remove any throwaway files created during Phase 4
rm -f /tmp/sut-test.txt
```

Do not delete `/tmp/mcp-wrapper.log`. Report to the user that cleanup is done.

## Tips

- **Log monitoring for long ops**: re-run `tail -n 20 /tmp/mcp-wrapper.log`
  every 40–60s. Growing output = still working; escalate only after several
  minutes of silence.
- **Ambiguous tool classification**: read the docstring in `--help`. If still
  unclear, treat it as mutating and let the user opt in.
- **Run confirmed tools sequentially** so log lines correlate cleanly to calls.
