# test-mcp — detailed workflow reference

Long-form companion to `SKILL.md`: config template, startup/readiness, discovery
and triage, invocation patterns, log analysis, cleanup, and troubleshooting.

---

## 1. Config template (annotated)

Write to `/tmp/test-mcp-config.json`. The `command` is any launcher on PATH or an
absolute path; `args` is its argument vector. Realistic multi-server example:

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

Simple published-package form:

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

Field-by-field:

| Field | Required | Meaning |
|-------|----------|---------|
| `mcpServers` | yes | Top-level map. Keys are server names used everywhere downstream (`--server <name>`, health path, log prefix). |
| `<name>` | yes | Logical server id (e.g. `tradingview-mcp`, `sut`). Appears in every log line as `[<name>]`. |
| `command` | yes | Executable launching the stdio server: `node`, `uvx`, `uv`, an absolute python path (`/…/.venv/bin/python`), or any binary on PATH. |
| `args` | yes | Argument vector. Examples: `["/abs/path/server.js"]` for node; `["-m", "pkg.module"]` for `python -m`; `["some-package@latest"]` for uvx. |
| `env` | no | Extra environment variables for the subprocess. Merged over the inherited env. `{}` is valid. |
| `disabled` | no | `false` to run. `true` keeps the server defined but not launched (e.g. `massive-mcp` above). |

You can define several servers; mount one with `--server <name>` or all
non-disabled ones by omitting `--server`. Ask the user for `command`/`args`/`env`
if not supplied — do not guess package names or paths.

---

## 2. Server startup + readiness check

The proxy is a **foreground uvicorn server that never exits on its own**. You
MUST background it, or it blocks the session:

```bash
# Bash with & — the ampersand returns control immediately
mcp-wrapper --config /tmp/test-mcp-config.json --http --server tradingview-mcp &

# In this harness, prefer the Bash tool's run_in_background: true instead of &.
```

Defaults: binds `127.0.0.1:8005`. Subprocess stderr is streamed to
`/tmp/mcp-wrapper.log` with lines of the form:
`[2026-03-05 22:12:18.972] [tradingview-mcp] <message>`.

Readiness loop — poll the health endpoint until it responds:

```bash
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8005/mcp-wrapper/tradingview-mcp/health >/dev/null; then
    echo "ready"; break
  fi
  sleep 2
done
```

Then confirm a clean boot:

```bash
tail -n 40 /tmp/mcp-wrapper.log
```

Healthy signature: `[<name>]` startup lines, no `Traceback (most recent call
last)`, no `ERROR`. If the process died on launch, the last lines show the
exception — see Troubleshooting.

---

## 3. Tool discovery and triage

### The client URL vs. --server

`--server <name>` auto-derives the client URL. It is exactly equivalent to:

```
--url http://127.0.0.1:8005/mcp-wrapper/<name>
```

So these two are identical:

```bash
mcp-wrapper --client --server tradingview-mcp --help
mcp-wrapper --client --url http://127.0.0.1:8005/mcp-wrapper/tradingview-mcp --help
```

Prefer `--server <name>` for readability; use `--url` only for a non-default host
or port.

### Discovery commands

```bash
# All mounted servers and their summaries
curl -s http://127.0.0.1:8005/mcp-wrapper/servers-info

# Per-server tool list with names, params, and docstrings
mcp-wrapper --client --server tradingview-mcp --help
```

Example (shape, not literal) of `--help` output:

```
Server: tradingview-mcp
Tools:
  get_quote(symbol: str)             -> latest quote
  list_symbols()                     -> available symbols
  search_symbols(query: str)         -> matches
  place_order(symbol: str, qty: int) -> order ack
```

### Classification rules

**Non-destructive** (safe to run by default) — the tool:
- Only reads, queries, lists, or inspects
- Has a `dry_run`/`preview` flag defaulting to `true`
- Name includes: `get_`, `list_`, `search_`, `query_`, `find_`, `show_`,
  `health`, `status`, `info`, `preview`

**Mutating** (skip unless the user names it) — the tool:
- Writes, indexes, updates, deletes, sends, places, or purges
- Name includes: `index_`, `create_`, `update_`, `delete_`, `remove_`,
  `clear_`, `purge_`, `send_`, `post_`, `write_`, `sync_`, `upload_`,
  `place_`, `order`
- Docstring mentions "creates", "writes", "removes", "sends", "places"

When ambiguous, read the docstring; if still unclear, classify as mutating and
require explicit opt-in.

### User confirmation prompt (exact pattern)

```
**Non-destructive tools discovered (candidates for testing):**
- list_symbols — no params
- get_quote — params: symbol (str)
- search_symbols — params: query (str)

**Mutating tools discovered (skipped unless you name them):**
- place_order — params: symbol (str), qty (int)

Which of the non-destructive tools should I run? I will use minimal valid inputs.
To test a mutating tool, name it and tell me exactly what inputs to use.
```

Do not proceed until the user replies. Do not infer consent from silence or from
earlier "test it" messages.

---

## 4. Invocation patterns

`--param:<key> <value>` supplies one argument; repeat for multiple params.

**No params:**
```bash
mcp-wrapper --client --server tradingview-mcp --tool list_symbols
```

**Scalar params** (string / number / bool — plain text):
```bash
mcp-wrapper --client --server tradingview-mcp --tool get_quote --param:symbol "AAPL"
mcp-wrapper --client --server sut --tool search --param:query "hello" --param:limit 5
```

**Array param** — JSON-encoded, in single quotes so the shell keeps it intact:
```bash
mcp-wrapper --client --server sut --tool index_files \
  --param:paths '["/tmp/sut-test.txt","/tmp/sut-test2.txt"]'
```

**Object param** — JSON-encoded:
```bash
mcp-wrapper --client --server sut --tool configure \
  --param:options '{"recursive":true,"depth":2}'
```

**Multiple mixed params:**
```bash
mcp-wrapper --client --server sut --tool search \
  --param:query "vectors" \
  --param:filters '{"type":"doc"}' \
  --param:limit 20
```

**Preparing throwaway inputs:** for a path param on a non-destructive tool,
create a minimal file in `/tmp` and track it for cleanup:

```bash
printf 'test content\n' > /tmp/sut-test.txt   # add to cleanup list
```

For mutating tools, use only the exact inputs the user supplied. Run tools
**sequentially**, not in parallel, so log lines correlate to individual calls.

---

## 5. Result and log analysis

### The CLI result

- **Exit code is the verdict:** `0` = pass, `1` = fail. Capture it:
  ```bash
  mcp-wrapper --client --server tradingview-mcp --tool get_quote --param:symbol "AAPL"
  echo "exit=$?"
  ```
- **Output format is not guaranteed.** Depending on the tool's return type the
  stdout may be JSON, plain text, or a mix. Read it as text. Do **not** assume
  JSON and do **not** look for a `"success": true` field — no such contract
  exists.
- **Errors surface on stderr** and, for a failed call, alongside exit code `1`.

### The log

`/tmp/mcp-wrapper.log` is the authoritative execution record. Correlate lines to
calls via the `[<name>]` prefix and timestamp ordering.

```bash
tail -n 30 /tmp/mcp-wrapper.log            # right after a call
tail -n 20 /tmp/mcp-wrapper.log            # re-run every 40–60s for long ops
```

### Verdict table

| Signal | Location | Verdict |
|--------|----------|---------|
| Exit code `0` | client process | call succeeded |
| Exit code `1` + stderr message | client process | call failed — read stderr |
| `[<name>]` log lines advance, no `ERROR`/traceback | log | clean execution |
| `Traceback (most recent call last)` under `[<name>]` | log | server-side exception (fail even if stdout looked fine) |
| `ERROR`/`WARNING` about missing env or credentials | log | misconfiguration — fix `env` in config |
| Zero new log lines for several minutes on a pending call | log | possible real hang — see Troubleshooting |

A call is **pass** only when exit code is `0` **and** the log shows no `ERROR` or
traceback for it. Exit `0` with a log traceback = fail; report the log evidence.

**Per-tool record** for the final report: tool name; exact command and inputs;
exit code; pass/fail; evidence (result snippet + decisive log line(s)).

---

## 6. Cleanup (default, always runs)

After all tests complete:

```bash
# 1. Stop the proxy you started (matched by its config path)
pkill -f "mcp-wrapper --config /tmp/test-mcp-config.json"

# 2. Remove the temp config
rm -f /tmp/test-mcp-config.json

# 3. Remove every throwaway file created during Phase 4
rm -f /tmp/sut-test.txt /tmp/sut-test2.txt
```

Do **not** delete `/tmp/mcp-wrapper.log` — it is shared across sessions and the
user may want historical output. Confirm to the user:

> "Proxy stopped, /tmp/test-mcp-config.json removed, throwaway test files
> removed, /tmp/mcp-wrapper.log left intact."

---

## 7. Troubleshooting

**Server won't start / health endpoint never responds**
1. `tail -n 60 /tmp/mcp-wrapper.log` — read the last exception.
2. Common causes:
   - Bad `command`/`args`: wrong absolute path to `server.js`, `node`/`uvx` not
     on PATH, wrong `-m` module name, venv python path typo.
   - Missing `env` the server checks at startup (e.g. `TV_MCP_AUTO_LAUNCH`).
   - Port 8005 already in use by a prior run.
   - You forgot to background the process, so it "hangs" — it is actually the
     foreground uvicorn server running normally; relaunch with `&` /
     `run_in_background: true`.
3. Port in use: `lsof -i :8005` to find the listener. If it is a stale
   mcp-wrapper, stop it with the `pkill -f "mcp-wrapper --config ..."` pattern
   targeting its config path, then restart.
4. Fix the config; relaunch and re-run the readiness loop.

**Tool call feels stuck / never returns**
1. Do NOT kill anything.
2. `tail -n 20 /tmp/mcp-wrapper.log`, re-check every 40–60s.
3. Growing output or new `[<name>]` lines = the op is running (indexing,
   downloads, searches take minutes). Keep waiting.
4. Only after **several minutes of zero new log activity** treat it as a real
   hang; report the last log lines and ask the user before acting.

**Confusing / unparseable CLI output**
1. Remember the output is not required to be JSON — a tool may return plain text.
   Judge by exit code, not by parsing.
2. If you did expect JSON (e.g. to extract a field) and got a parse error, first
   confirm the exit code: a `1` means it is an error message, not data.
3. For array/object params, a common failure is un-encoded or shell-mangled JSON.
   Use single quotes: `--param:paths '["/tmp/a.txt"]'`. Validate independently:
   `echo '<json>' | python3 -m json.tool`.
4. Re-check the tool name and required params via
   `mcp-wrapper --client --server <name> --help`.

**Tool classified as mutating but user wants to test it**
The user must name the tool explicitly and provide exact inputs. Never
auto-generate inputs for mutating tools. For irreversible actions (e.g.
`place_order`, `delete_collection`), confirm once more before firing.
