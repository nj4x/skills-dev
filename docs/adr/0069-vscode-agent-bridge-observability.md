---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0069: Observability for vscode-agent-bridge (MCP server + VS Code extension)

**Date:** 2026-08-29

**Status:** Implemented

## Context

vscode-agent-bridge (MCP server in `mcp/vscode-agent-bridge/` + TypeScript extension in `vscode-agent-bridge/`) has zero observability. No Python `logging` calls anywhere in `bridge/*.py` or `server.py`; the extension has no `vscode.OutputChannel` and no file logging — only `console.log` (DevTools-only) and user-facing error popups. All task state lives in-memory in `BridgeQueue` and is lost on server restart.

This was surfaced concretely: `poll_peer_agent` returned `{status: failed, reason: cancelled}` for a task the user believed had actually completed successfully. There was no way to check — no log recorded whether the TaskCancel hook fired before or after genuine completion, or whether the cancel event itself was spurious. The bridge's only observability is its return value at poll time.

Sibling package `mcp/mcp-vectors` already has a working logging convention (`server.py:87-128`): Python `logging` with `RotatingFileHandler`, `~/.mcp-vectors/logs/mcp-vectors.log`, 10 MB / 3 backups, format `"%(asctime)s [%(levelname)s] [PID:%(process)d] %(name)s: %(message)s"` with local-timezone timestamps.

## Decision

**Log layout** — single rotating file, all events in one chronological stream:

- Bridge log: `~/.vscode-agent-bridge/logs/vscode-agent-bridge.log`, `RotatingFileHandler`, 10 MB / 3 backups (matching mcp-vectors convention exactly).
- Directory creation: on startup, ensure `~/.vscode-agent-bridge/logs/` exists via `mkdir -p`; treat creation failure as a logging-subsystem failure per the non-fatal policy (see below).
- Format: `%(asctime)s [%(levelname)s] [PID:%(process)d] [task_id=%(task_id)s] %(name)s: %(message)s` with local-timezone timestamps.
- Every log message carries a `task_id=` field (empty if no task is associated) so lines remain greppable by task despite the single shared file.
- Retention: `RotatingFileHandler` rotates files automatically on size threshold (10 MB); crashed-instance files accumulate until the next size rotation.

**MCP server (Python)** — `logging` module, Python `RotatingFileHandler`. Identical to mcp-vectors convention (server.py:87-128), adapted for `vscode-agent-bridge` paths and `task_id=` field injection. Task id context propagation: a `logging.Filter` subclass reads `task_id` from a `contextvars.ContextVar` set at task dispatch time and injects `task_id=<id>` (or `task_id=` when unset) into every LogRecord. The filter is attached to the root vscode-agent-bridge logger at initialization, so every message is automatically tagged without per-call overhead.

**Event set:**
- Queue (INFO): task submitted (id, workspace), every status transition (queued→dispatched→answered/failed/cancelled) with reason
- HookServer (INFO): every `/hook` POST received (hookName, task id), every WS connect/disconnect
- Instance (INFO): VS Code process spawn (pid, workspace, port), process exit (exit code)
- Bridge (INFO): `_pump()` entry/exit
- Bridge (DEBUG): `sweep_expired()` runs (5s periodic invocations), per-poll-interval heartbeats
- ERROR: exceptions, unexpected WS close

**Internal log state → MCP return mapping:**
- Log state `answered` → `poll_peer_agent` returns `{status: "answered", answer, command, ...}`
- Log state `failed` with reason `timeout` → `{status: "failed", reason: "timeout"}`
- Log state `failed` with reason `cancelled` → `{status: "failed", reason: "cancelled"}`
- Log state `failed` with reason `instance_down` → `{status: "failed", reason: "instance_down"}`
- Log state `pending` (dispatched but not yet answered/failed) → `poll_peer_agent` returns `{status: "pending", tool_uses, last_event_at}`

**VS Code extension (TypeScript)** — `vscode.OutputChannel` named `"Agent Bridge"` (visible in Output panel without DevTools). Events logged at INFO: WS connected/disconnected to bridge, VS Code URI scheme invocation (cline-sr task URI, prompt length only, not content). Errors at ERROR level. OutputChannel alone is sufficient observability for the extension's peer; it survives interactive debugging without file-write permissions and does not create a retention/sweep burden. DEBUG level is omitted: OutputChannel is ephemeral (discarded when VS Code closes) and the extension's observability is limited to user-facing events and errors, not internal heartbeats.

**Failure policy** — Logging subsystem failures (disk full, permission denied, `~/.vscode-agent-bridge/logs/` unwritable or uncreatable) are non-fatal. Server startup succeeds even if `RotatingFileHandler` cannot initialize or `mkdir -p` fails; a single warning is emitted to stderr and the server runs without file logging. Extension OutputChannel creation failure is treated identically — non-fatal; errors surface only to the VS Code developer console and the extension continues running without file logging. Observability must never take down the system it observes.

**Scope: single-instance server assumed** — the log file `~/.vscode-agent-bridge/logs/vscode-agent-bridge.log` is written by one MCP server process per user account. Concurrent multi-process writes are out-of-scope; they would require a process-safe rotation mechanism (e.g., WatchedFileHandler or per-PID log files), which is not implemented. The `[PID:%(process)d]` field in the log format aids debugging of sequential restarts, not concurrent writers.

**Lineage:** No SRS/FS anchor. This repo's `.data/requirements/` corpus does not exist, and prior ADRs 0064–0068 (including the sibling ADR-0068 for the same package) carry no `source-srs` frontmatter — this is internal tooling observability, not a product requirement, so this ADR follows that precedent and is unanchored.

## Consequences

**Positive:**
- The `poll_peer_agent` cancelled-vs-completed ambiguity that motivated this ADR becomes diagnosable: task log shows exact TaskCancel POST timestamp relative to any TaskComplete POST.
- Consistent logging convention across `mcp/` packages (mcp-vectors, vscode-agent-bridge) lowers the cost of debugging either.

**Negative:**
- Task logs from simultaneous parallel requests within a single server process are interleaved in one file (but `task_id=` fields make parsing and filtering straightforward).
- `RotatingFileHandler` is slower than unbuffered writes (accepted: observability cost is small vs. operational value).
- Bridge must handle `RotatingFileHandler` initialization failure (non-fatal, fallback to stderr only).
- The log state → MPC return mapping exists to aid human troubleshooting but is not machine-enforced; implementers must manually verify consistency between the internal logging states used and the MCP return values they produce.
