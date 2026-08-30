---
artifact-type: research
title: Why vscode-agent-bridge needs a VS Code extension
date: 2026-08-29
---

# Why vscode-agent-bridge Needs a VS Code Extension

## Summary

The vscode-agent-bridge system is an MCP server + VS Code extension pair that lets Claude Code delegate questions to cline-sr (a peer Cline agent) running in a **separate, dedicated VS Code window**. The extension cannot be replaced by an MCP server alone because the extension:

1. **Installs and manages hook scripts** in cline-sr's hook directory — accessible only from the VS Code extension host
2. **Holds the liveness WebSocket** to the bridge — only possible from within a VS Code window context
3. **Invokes cline-sr's URI handler** to submit tasks — requires the `vscode.env` API (only available inside VS Code)

These three responsibilities form the bridge's connection to cline-sr and are **unreachable from the Python MCP server process alone**.

---

## Architecture Overview

```
┌─────────────────────┐
│   Claude Code       │
│  MCP Client         │
└──────────┬──────────┘
           │ ask_peer_agent / submit_to_peer_agent / poll_peer_agent
           ▼
┌─────────────────────────────────────────────────────┐
│  MCP Server Process (vscode-agent-bridge)           │
│  ┌──────────────┐  ┌────────────┐  ┌─────────────┐ │
│  │ BridgeQueue  │  │ HookServer │  │ Instance    │ │
│  │ (in-mem      │  │ (HTTP /    │  │ Manager     │ │
│  │  task state) │  │  hook,     │  │ (spawns     │ │
│  │              │  │  WS /ws)   │  │  code CLI)  │ │
│  └──────────────┘  └────────────┘  └─────────────┘ │
└──────────────┬──────────────────────────────────────┘
               │ TCP 127.0.0.1:$BRIDGE_PORT
               │ (HTTP, WebSocket)
               ▼
┌──────────────────────────────────────────────────────┐
│  Dedicated VS Code Window (separate process)         │
│  ┌────────────────────────────────────────────────┐  │
│  │  vscode-agent-bridge Extension (TypeScript)    │  │
│  │  ┌─────────────────┐  ┌──────────────────────┐ │  │
│  │  │ Hook installer  │  │ WebSocket client &   │ │  │
│  │  │ (writes to      │  │ task submitter       │ │  │
│  │  │ ~/Documents/    │  │ (vscode.env API)     │ │  │
│  │  │ Cline/Hooks/)   │  │                      │ │  │
│  │  └─────────────────┘  └──────────────────────┘ │  │
│  └────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────┐  │
│  │  cline-sr Agent (Cline peer)                   │  │
│  │  - Runs tasks in live workspace               │  │
│  │  - Invoked via URI scheme by extension        │  │
│  │  - Fires lifecycle hooks (TaskStart, etc.)    │  │
│  └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## Why Each Component Is Needed

### 1. Hook Script Installation (Extension Responsibility)

**What:** The extension idempotently installs five bash scripts to `~/Documents/Cline/Hooks/`:
- TaskStart, PreToolUse, PostToolUse, TaskComplete, TaskCancel

**Why not the MCP server?**
- These scripts must live in a user-writable, OS-specific directory outside the vscode-agent-bridge repo
- They must be installed *once per machine*, not per MCP server process (the server restarts; the scripts persist)
- They need to be owned and versioned by the extension so the extension can detect staleness and update them (via SHA256 hash)

**Why the extension can do it:**
- Extension code runs in the **VS Code extension host** on the user's machine, with access to `fs` APIs and the user's home directory
- Extension activation fires on every VS Code window startup (`onStartupFinished`), making it the natural place to idempotently refresh these scripts

**Code:** `/vscode-agent-bridge/src/extension.ts:163–202` (the `installHooks()` function)

### 2. Liveness WebSocket (Extension Responsibility)

**What:** The extension establishes a persistent WebSocket connection to `ws://127.0.0.1:$BRIDGE_PORT/ws` and holds it open for the window's lifetime.

**Why not the MCP server?**
- The MCP server cannot distinguish between "the VS Code window crashed" and "the MCP server process crashed"
- The `code` CLI hands off to Electron and exits immediately (per design #70 in `instance.py:97`), so the server cannot use process exit as the liveness signal
- Only the window itself can prove it is alive

**Why the extension can do it:**
- The extension is code running **inside** the VS Code window
- When the window closes or crashes, the WebSocket automatically terminates
- The MCP server watches the socket: when it closes, the server knows the instance is gone and marks it disconnected (invokes `HookServer.mark_disconnected()` → `Queue.fail_in_flight("instance_down")`)

**Flow:**
1. MCP server spawns `code --user-data-dir ~/.vscode-agent-bridge/data` and passes `BRIDGE_PORT` in env
2. VS Code starts, activates the extension (line 44 in `extension.ts`)
3. Extension reads `BRIDGE_PORT` from `process.env` (line 56)
4. Extension connects WebSocket to bridge (line 70, `connect(port)`)
5. Bridge receives WS open event → calls `instance.mark_connected()` → signals that the window is ready (line 123 in `instance.py`)

**Code:** `/vscode-agent-bridge/src/extension.ts:93–135` (the `connect()` function); `/vscode-agent-bridge/src/extension.ts:34–37` (WebSocket persistent state)

### 3. Task Submission (Extension Responsibility)

**What:** The extension receives task submission frames over the WebSocket (`{type: "submit", prompt: ...}`) and invokes cline-sr's URI handler: `vscode://cline-sr.cline-sr/task?prompt=<encoded>`.

**Why not the MCP server?**
- The MCP server is a Python process; it has no access to the VS Code extension host's URI scheme system
- The URI scheme is part of the VS Code IPC and activation system — only reachable from inside VS Code (via the `vscode.env.openExternal()` API)

**Why the extension can do it:**
- It is **inside** the VS Code window, so it can call `vscode.env.openExternal(uri)`
- This triggers the cline-sr extension's URI handler in the *same* window (local activation), submitting the task to the peer agent synchronously
- The extension also logs the submission for observability (line 138 in `extension.ts`)

**Flow:**
1. MCP server calls `HookServer.dispatch(prompt)` when a task is ready to run
2. HookServer sends `{"type": "submit", "prompt": "..."}` over the WS to the extension (line 81 in `bridge.py`)
3. Extension receives the message (line 106 in `extension.ts`), extracts the prompt, and calls `submitToClineSr(prompt)` (line 114)
4. `submitToClineSr` builds the URI and invokes it (lines 137–150)
5. cline-sr extension receives the URI and starts the task

**Code:** `/vscode-agent-bridge/src/extension.ts:137–150` (task submission); `/vscode-agent-bridge/src/extension.ts:106–116` (message dispatch)

### 4. Hook Script Lifecycle Integration (Extension + MCP Server)

**What:** The hook scripts run during cline-sr's task lifecycle. Each script reads `$BRIDGE_PORT` and POSTs to the MCP server's `/hook` endpoint, which updates task state in the queue.

**Why this architecture works:**
- **Extension job:** Install the scripts and verify hooks are enabled in cline-sr settings (lines 54–68 in `extension.ts`)
- **Script job:** Fire-and-forget POST to the bridge's HTTP server with lifecycle metadata (TaskStart, TaskComplete, etc.)
- **MCP server job:** Receive the POST, extract the task ID from metadata, correlate it to the in-flight queue record, and update state (ADR-0070: hook-event correlation)

**Example flow (TaskComplete):**
1. cline-sr finishes the task and fires the TaskComplete hook
2. Hook script (bash) reads `$BRIDGE_PORT` and POSTs `{hookName: "TaskComplete", taskComplete: {taskMetadata: {taskId: "..."}}, result, command}` to `http://127.0.0.1:$BRIDGE_PORT/hook`
3. MCP server's HookServer receives it, calls `Queue.complete(answer, command, cline_task_id=taskId)`
4. Queue correlates the taskId to the bridged record, sets status to "answered"
5. `poll_peer_agent` returns `{status: "answered", answer, command}`

**Code:**
- Hook script template: `/vscode-agent-bridge/hooks/TaskStart` (and others)
- Queue binding logic: `mcp/vscode-agent-bridge/bridge/queue.py` (bind_cline_task, complete, cancel)
- Hook server receiver: `mcp/vscode-agent-bridge/bridge/hookserver.py:_handle_hook()`

---

## What the MCP Server Alone Cannot Do

**Question:** Why can't the Python MCP server do all of this?

**Answer:** The MCP server is a subprocess with **no privileged access** to the user's machine:
1. **No VS Code APIs** — cannot call `vscode.env.openExternal()` or install into extension directories
2. **No filesystem access to `~/Documents/`** — the MCP process runs in isolation; even if it had the path, it would violate the sandboxing contract
3. **No real-time window liveness detection** — cannot tell if a window is alive without holding a connection from inside it
4. **No way to prove it is not stalled** — the only proof of liveness is a message from code *inside* the window

The extension bridges this gap: it is **trusted code running with user-level privileges inside VS Code**, so it can:
- Read/write to home directory paths
- Call VS Code APIs
- Access the VS Code extension activation system and URI schemes
- Signal liveness by maintaining the WebSocket connection

---

## Reference to Design Documents

- **ADR-0068** (`docs/adr/0068-vscode-agent-bridge-orchestration-module.md`) — Orchestration design; includes sequence diagrams (Diagram 1 shows hook installation, Diagram 2 shows task dispatch and liveness flow)
- **ADR-0069** (`docs/adr/0069-vscode-agent-bridge-observability.md:1–50`) — Observability: why the extension needs `vscode.OutputChannel`; non-fatal logging policy
- **ADR-0070** (`docs/adr/0070-vscode-agent-bridge-hook-event-correlation.md`) — Hook event correlation: how taskId from TaskStart hook is bound to the queue record and used to correlate TaskComplete/TaskCancel events
- **Setup guide** (`docs/research/vscode-agent-bridge-end-to-end-setup.md`) — End-to-end setup including extension installation and hook verification

---

## Extension Code Structure

| Module | Responsibility | Lines |
|--------|-----------------|-------|
| `vscode-agent-bridge/src/extension.ts` | Activation, hook installation, WebSocket liveness, task submission | 1–207 |
| `vscode-agent-bridge/hooks/*` | Five bash hook script templates; POSTs lifecycle events to `/hook` endpoint | Per-script ~12 lines |
| `vscode-agent-bridge/package.json` | Metadata, activation event, dependencies (ws for WebSocket) | 1–30 |
| `mcp/vscode-agent-bridge/bridge/hookserver.py` | HTTP `/hook` receiver, WebSocket `/ws` holder, task dispatcher | ~200 lines |
| `mcp/vscode-agent-bridge/bridge/instance.py` | VS Code process lifecycle, BRIDGE_PORT passthrough, liveness event handling | ~105 lines |

---

## Summary Table

| Responsibility | Why Extension | Why Not MCP Server |
|---|---|---|
| Install hook scripts to `~/Documents/Cline/Hooks/` | Has `fs` APIs, user-level privileges, extension activation hook | No filesystem access, subprocess sandbox |
| Hold liveness WebSocket | Code runs inside VS Code window, can maintain persistent connection | Cannot prove it is not stalled without in-window signal |
| Invoke `vscode://cline-sr.cline-sr/task?...` URI | Has `vscode.env.openExternal()` API | No VS Code API access |
| Verify hooks enabled in cline-sr settings | Can read `~/.cline-sr/data/globalState.json` from extension context | Would require user-level file access |
| Dispatch hook POSTs to bridge | Sends WebSocket messages to MCP server | ✓ MCP server receives and processes (correct place) |
| Queue task state & correlate hook events | ✓ Correct place (MCP server owns queue) | (Depends on extension for liveness + hook metadata) |

---

## Conclusion

The extension is not optional infrastructure — it is a **required peer** in a **two-process architecture**:
- **MCP Server:** Orchestrates queue state, spawns VS Code, manages timeouts
- **Extension:** Bridges the MCP server to cline-sr by holding liveness, submitting tasks, and managing hook scripts

Removing the extension would require:
1. Moving hook installation to cline-sr itself (breaking the separation of concerns; cline-sr would own bridge internals)
2. Replacing liveness detection with polling or heartbeats (losing the clean "window alive ⟺ socket open" signal)
3. Finding a way to invoke cline-sr's URI handler from a Python subprocess (not possible in VS Code's architecture)

The extension is the extension host's representative in the bridge system.
