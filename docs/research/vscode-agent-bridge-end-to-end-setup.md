# vscode-agent-bridge End-to-End Setup Guide

**Research Date:** 2026-08-29  
**Scope:** Clean environment setup, primary source verification

## Overview

The vscode-agent-bridge is a two-component system:
1. **MCP Server** (`mcp/vscode-agent-bridge/` — Python/AsyncIO)
2. **Companion VS Code Extension** (`vscode-agent-bridge/` — TypeScript/Node)

Together they enable Claude Code to delegate long tasks to cline-sr (a peer agent) running in a dedicated VS Code window.

---

## 1. Prerequisites

### 1.1 System Requirements

| Requirement | Purpose | Verification Command |
|---|---|---|
| **Python ≥3.10** | MCP server runtime | `python3 --version` |
| **Node.js & npm** | Extension build + dependencies | `npm --version` |
| **TypeScript compiler** | Extension compilation | `tsc --version` (installed via npm) |
| **VS Code CLI** (`code` binary) | Spawn dedicated bridge window | `code --version` |
| **uv package manager** | Python project management (MCP server) | `uv --version` |
| **cline-sr VS Code extension** | Peer agent that receives delegated tasks | (Check: VS Code > Extensions > Search "cline-sr") |

### 1.2 Verify Prerequisites

```bash
# Python
python3 --version  # must be >= 3.10

# Node.js / npm
node --version
npm --version

# VS Code CLI (must be in PATH)
code --version

# uv package manager (https://docs.astral.sh/uv/getting-started/)
uv --version

# cline-sr extension (marketplace search, or: VS Code menu > Extensions > Search "cline-sr")
# Install if not present
```

### 1.3 cline-sr Configuration

The cline-sr extension **must have Hooks enabled** for the bridge to receive lifecycle events. This is the default, but can be verified/changed:
- In cline-sr's VS Code instance: Settings Webview > enable "Hooks"
- Config file: `~/.cline-sr/data/globalState.json` should have `"hooksEnabled": true` (or absent, which defaults to true)

---

## 2. Installation: MCP Server

### 2.1 Clone / Locate the Repo

```bash
cd /path/to/skills-dev  # or clone: git clone <repo-url>
```

### 2.2 Install MCP Server Dependencies

**Location:** `/path/to/skills-dev/mcp/vscode-agent-bridge/`

```bash
cd mcp/vscode-agent-bridge

# Create virtual environment and install
uv venv .venv
uv pip install -e ".[dev]"  # includes pytest, pytest-asyncio for tests

# Verify installation
.venv/bin/python -c "from bridge.bridge import Bridge; print('Bridge import OK')"
.venv/bin/pytest tests/  # optional: run test suite
```

**Key Details** (from `pyproject.toml` at `/Users/r.herasymenk/workspace/skills-dev/mcp/vscode-agent-bridge/pyproject.toml`):
- **Requires:** Python ≥3.10
- **Core Dependencies:**
  - `mcp[cli]>=2.0.0` — MCP framework with CLI support
  - `aiohttp>=3.9.0` — Async HTTP for hook server
- **Entry Point:** `vscode-agent-bridge = "server:main"` (callable as `vscode-agent-bridge` after install)

---

## 3. Installation: Companion Extension

### 3.1 Build the Extension

**Location:** `/path/to/skills-dev/vscode-agent-bridge/`

```bash
cd vscode-agent-bridge

# Install Node dependencies (ws 8.18.0 for WebSocket client, TypeScript devDeps)
npm install

# Compile TypeScript to JavaScript
npm run compile
# Produces: ./out/extension.js (from src/extension.ts)
```

**Key Details** (from `package.json` at `/Users/r.herasymenk/workspace/skills-dev/vscode-agent-bridge/package.json`):
- **Engine:** VS Code ^1.75.0
- **Main:** `./out/extension.js`
- **Activation:** `onStartupFinished` (runs when any VS Code window opens)
- **Publishers:** nj4x (private extension)

### 3.2 Install Extension into VS Code

The extension does **not** need to be published; it can be symlinked into the local extensions directory:

```bash
# From vscode-agent-bridge/ directory
npm run install-dev
# Runs: bash scripts/install-dev.sh
# Creates symlink: ~/.vscode/extensions/nj4x.vscode-agent-bridge-0.1.0 -> repo root
```

**What the extension does on activation (every window):**
1. **Idempotently installs hook scripts** to `~/Documents/Cline/Hooks/` (5 scripts: `TaskStart`, `PreToolUse`, `PostToolUse`, `TaskComplete`, `TaskCancel`)
   - Checks sha256 to skip if unchanged
   - Never overwrites foreign scripts (warns instead)
   - Marker line `vscode-agent-bridge hook` identifies scripts owned by the bridge
2. **In the dedicated bridge window only** (when `BRIDGE_PORT` env var is set):
   - Checks `~/.cline-sr/data/globalState.json` for `hooksEnabled` flag
   - Holds WebSocket connection to `ws://127.0.0.1:$BRIDGE_PORT/ws` (reconnects every 3s)
   - Submits tasks to cline-sr via `vscode://cline-sr.cline-sr/task?prompt=...` URI handler

**Verification after symlink:**
- Reload any VS Code window (Cmd+Shift+P > "Reload Window")
- Check Output Pane > "Agent Bridge" for log messages
- Verify hooks in `~/Documents/Cline/Hooks/` have been created

---

## 4. Claude Code MCP Registration

### 4.1 Registration Method

The MCP server must be registered in Claude Code's settings so it is launched when Claude Code starts.

**Current live registration** (from `~/.claude.json` user config):
```json
{
  "mcpServers": {
    "vscode-agent-bridge": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/r.herasymenk/workspace/skills-dev/mcp/vscode-agent-bridge",
        "vscode-agent-bridge"
      ],
      "env": {}
    }
  }
}
```

### 4.2 Register the Server

**Option A: Manual CLI (after first-time install)**

```bash
claude mcp add vscode-agent-bridge \
  uv run --directory /path/to/skills-dev/mcp/vscode-agent-bridge vscode-agent-bridge
```

**Option B: Edit `~/.claude.json` directly**

```json
{
  "mcpServers": {
    "vscode-agent-bridge": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/skills-dev/mcp/vscode-agent-bridge",
        "vscode-agent-bridge"
      ],
      "env": {}
    }
  }
}
```

**Key Points:**
- **Command:** `uv run --directory <server-dir> vscode-agent-bridge`
  - `uv run` activates the project's `.venv` and runs the entry point `vscode-agent-bridge` (from `pyproject.toml`)
- **Alternative (if uv not in PATH):** `<server-dir>/.venv/bin/vscode-agent-bridge`
- **No env vars required** by default; optional:
  - `BRIDGE_ASK_TIMEOUT=180` — blocking ask() timeout in seconds (default: 180)
  - `BRIDGE_ASYNC_TIMEOUT=1800` — submit/poll expiry in seconds (default: 1800)

### 4.3 Restart Claude Code

After registration, restart Claude Code for the MCP server to launch:

```bash
claude  # Start Claude Code CLI
# OR reload in the IDE
```

---

## 5. Configuration & State Directories

### 5.1 MCP Server State

**Location:** `~/.vscode-agent-bridge/`

| Path | Purpose |
|---|---|
| `~/.vscode-agent-bridge/data/` | Dedicated VS Code instance workspace (user data directory); persists across sessions |
| `~/.vscode-agent-bridge/data/User/settings.json` | Seeded settings (workspace trust disabled, updates off, telemetry off) |
| `~/.vscode-agent-bridge/data/logs/` | VS Code extension host logs (Electron process logs) |
| `~/.vscode-agent-bridge/logs/` | MCP server logs (one file per session: `vscode-agent-bridge.log` named by start timestamp) |

### 5.2 cline-sr State

**Location:** `~/.cline-sr/`

| Path | Purpose |
|---|---|
| `~/.cline-sr/data/globalState.json` | Extension settings; bridge reads `hooksEnabled` flag here |
| `~/Documents/Cline/Hooks/` | Hook scripts installed by bridge extension (5 scripts) |

### 5.3 No Additional Configuration Required

- **API keys / provider config:** Not needed for the bridge itself. cline-sr's own provider config (OpenAI, Claude, etc.) is separate.
- **Port selection:** HookServer binds to `127.0.0.1:0` (OS-assigned ephemeral port); passed to dedicated VS Code via `BRIDGE_PORT` env var.
- **Firewall:** All communication is localhost only.

---

## 6. Verification: Integration Test

### 6.1 Check MCP Server is Registered

```bash
# In Claude Code, invoke an MCP tool
claude ask-peer-agent --help
# OR: claude delegate-to-cline --help (skill that wraps the bridge)
```

### 6.2 Verify Tools Are Exposed

In Claude Code, the following MCP tools should be available:

| Tool | Purpose | Blocking? |
|---|---|---|
| `ask_peer_agent(question, workspace)` | Submit task to cline-sr and block for answer (180s timeout) | Yes |
| `submit_to_peer_agent(question, workspace)` | Submit task without waiting | No |
| `poll_peer_agent(handle)` | Check status of a submitted task | No |
| `close_peer_agent()` | Close the dedicated bridge window (only if no tasks in flight) | N/A |
| `get_logs_for_session(handle=None)` | Retrieve session/task log paths for debugging | N/A |

**Listing available tools** (Claude Code CLI):
```bash
claude mcp list  # Shows registered servers
```

### 6.3 End-to-End Smoke Test

#### 6.3.1 From Claude Code

```bash
# Trigger delegation (via delegate-to-cline skill or Agent tool with subagent_type="cline")
# This submits a task to cline-sr and waits for the answer

# Example: use the Agent tool in a Claude Code session
# Agent({
#   subagent_type: "cline",
#   description: "Quick test task",
#   prompt: "List the files in /tmp using `ls`"
# })
```

#### 6.3.2 From Command Line (Low-Level)

```bash
# 1. Start the MCP server directly (not via Claude Code)
cd /path/to/skills-dev/mcp/vscode-agent-bridge
uv run vscode-agent-bridge

# 2. Observe logs (in another terminal)
tail -f ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log

# 3. Watch VS Code bridge window spawn
# Check: System → Activity Monitor or ps aux | grep "code"
# Window location: ~/.vscode-agent-bridge/data/

# 4. Verify hook scripts in place
ls -la ~/Documents/Cline/Hooks/
# Should show: TaskStart PreToolUse PostToolUse TaskComplete TaskCancel (all 755)
```

### 6.4 Debugging: Check Logs

**MCP Server Log:**
```bash
cat ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log | grep -i "error\|instance\|connected"
# Format: ISO timestamp [task_id=<id>] [level] message
# Grep by task ID to isolate one request's flow
```

**VS Code Extension Log:**
```bash
ls -ltr ~/.vscode-agent-bridge/data/logs/
# Newest directory = latest instance spawn
cat "~/.vscode-agent-bridge/data/logs/$(ls -t ~/.vscode-agent-bridge/data/logs | head -1)"/exthost.log
```

**Get Logs Programmatically** (within a task):
```python
# Using the MCP tool
result = await get_logs_for_session(handle="<task_id>")
print(result["session_log"])  # ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log
print(result["vscode_exthost_log"])  # ~/.vscode-agent-bridge/data/logs/<timestamp>/
```

---

## 7. Current README Status

### 7.1 MCP Server README
**Location:** `/Users/r.herasymenk/workspace/skills-dev/mcp/vscode-agent-bridge/README.md`  
**Current State:** **Minimal**
- Lists only the three MCP tools (ask_peer_agent, submit_to_peer_agent, poll_peer_agent)
- Dev loop section shows `uv venv .venv && uv pip install -e ".[dev]" && pytest`
- **Missing:**
  - Entry point clarification (`vscode-agent-bridge` script from `pyproject.toml`)
  - Claude Code registration command
  - Prerequisites (Python 3.10+, uv, VS Code CLI)
  - Troubleshooting section
  - Environment variable documentation (BRIDGE_ASK_TIMEOUT, BRIDGE_ASYNC_TIMEOUT)

### 7.2 Companion Extension README
**Location:** `/Users/r.herasymenk/workspace/skills-dev/vscode-agent-bridge/README.md`  
**Current State:** **Complete for extension internals**
- Describes what the extension does (hook installation, liveness WebSocket, task submission)
- Dev loop: `npm install`, `npm run compile`, `npm run install-dev`
- **Missing:**
  - Link to MCP server README
  - Instructions for end-to-end setup (MCP server installation is prerequisite)
  - cline-sr prerequisite + Hooks enablement requirement
  - Integration with Claude Code settings

---

## 8. Complete Setup Walkthrough

For a fresh clone, a user would perform:

### 8.1 Prerequisites (System)
```bash
# Verify prerequisites
python3 --version  # >= 3.10
node --version
npm --version
code --version
uv --version

# Install cline-sr extension in any VS Code window (marketplace or gh release)
# Verify Hooks are enabled: cline-sr settings > Hooks toggle = ON
```

### 8.2 Install MCP Server
```bash
cd /path/to/skills-dev/mcp/vscode-agent-bridge
uv venv .venv
uv pip install -e ".[dev]"
```

### 8.3 Install & Activate Companion Extension
```bash
cd /path/to/skills-dev/vscode-agent-bridge
npm install
npm run compile
npm run install-dev
# Reload any VS Code window (Cmd+Shift+P > Reload)
# Verify hook scripts in ~/Documents/Cline/Hooks/ (ls -la)
```

### 8.4 Register MCP Server with Claude Code
```bash
# Option A: CLI
claude mcp add vscode-agent-bridge \
  uv run --directory /path/to/skills-dev/mcp/vscode-agent-bridge vscode-agent-bridge

# Option B: Edit ~/.claude.json directly (see Section 4.2)
```

### 8.5 Restart Claude Code
```bash
claude  # Starts fresh with MCP server
```

### 8.6 Verify Integration
```bash
# In Claude Code:
# - Use Agent({ subagent_type: "cline", ... }) or delegate-to-cline skill
# - Watch ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log for activity

# In terminal:
tail -f ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log
```

---

## 9. Key Source Files & Line References

| File | Purpose | Key Lines |
|---|---|---|
| `/mcp/vscode-agent-bridge/pyproject.toml` | Server config, entry point, dependencies | 1–29 |
| `/mcp/vscode-agent-bridge/server.py` | MCP tool definitions, lifespan context | 48–153 |
| `/mcp/vscode-agent-bridge/bridge/bridge.py` | Orchestration (queue, instance, hooks, pump/sweep) | 42–203 |
| `/mcp/vscode-agent-bridge/bridge/instance.py` | VS Code window lifecycle (spawn, reuse, settings) | 21–105 |
| `/vscode-agent-bridge/src/extension.ts` | Extension activation, hook installation, WebSocket, task submission | 44–202 |
| `/vscode-agent-bridge/package.json` | Node config, activation events | 1–30 |
| `/vscode-agent-bridge/scripts/install-dev.sh` | Symlink extension into `~/.vscode/extensions/` | 1–20 |
| `/vscode-agent-bridge/hooks/TaskStart` | Hook script template (forward to bridge /hook endpoint) | 1–12 |
| `/docs/adr/0068-vscode-agent-bridge-orchestration-module.md` | Architecture & sequence diagrams | Full document |
| `/CONTEXT.md` (Domain section) | Terminology & logging structure | Lines 63–76 |

---

## 10. Environmental Variables

**Set by MCP server (not by user):**
- `BRIDGE_PORT` — Ephemeral HTTP server port (127.0.0.1:N), passed to `code` CLI via env, read by extension from `process.env.BRIDGE_PORT`

**Configurable (optional, in Claude Code settings or shell):**
| Variable | Default | Effect |
|---|---|---|
| `BRIDGE_ASK_TIMEOUT` | 180 (seconds) | Blocking `ask_peer_agent()` deadline |
| `BRIDGE_ASYNC_TIMEOUT` | 1800 (seconds) | `submit_to_peer_agent()` expiry window |

**Set by extension (not by user):**
- `RECONNECT_DELAY_MS` = 3000 — WebSocket reconnection interval

---

## 11. Known Limitations & Troubleshooting

| Issue | Cause | Resolution |
|---|---|---|
| Bridge window doesn't spawn | `code` CLI not in PATH | Add VS Code to PATH: `export PATH="/Applications/Visual Studio Code.app/Contents/Resources/app/bin:$PATH"` (macOS) |
| Extension won't connect to bridge | Hooks disabled in cline-sr | Open cline-sr settings > Hooks toggle ON |
| Hook scripts not installed | Extension not activated | Reload any VS Code window after `npm run install-dev` |
| `ask_peer_agent` times out after 180s | Task takes > 180s | Use `submit_to_peer_agent` + `poll_peer_agent` (async) instead; default timeout is 1800s for async |
| Logs not appearing | Log directory not writable | Check `chmod 755 ~/.vscode-agent-bridge/logs/` |
| MCP server crashes on startup | `mcp[cli]` not installed | Re-run `uv pip install -e ".[dev]"` in server directory |

---

## 12. References & Documentation

- **ADR-0068:** `/docs/adr/0068-vscode-agent-bridge-orchestration-module.md` — Architecture & sequence diagrams
- **ADR-0069:** `/docs/adr/0069-vscode-agent-bridge-observability.md` — Logging & observability
- **ADR-0070:** `/docs/adr/0070-vscode-agent-bridge-hook-event-correlation.md` — Hook event flow & task/event binding
- **Skill:** `/engineering/delegate-to-cline/SKILL.md` — Higher-level delegation interface
- **Agent Config:** `/.claude/agents/cline.md` — cline agent type configuration
- **Domain Terminology:** `/CONTEXT.md` (lines 63–76)
- **Issue #67:** Wayfinder map (design discussion)
- **Issue #70, #71:** Extension design discussions
