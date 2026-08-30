# vscode-agent-bridge

MCP server letting Claude Code delegate a task to cline-sr — a separate VS
Code process — via a persistent companion window, replacing the bash-poll
`cline-bridge`. Task submission rides a WebSocket the companion extension
holds open; lifecycle events (start, tool use, completion, cancel) arrive
over HTTP from cline-sr's native hook scripts instead of filesystem polling.

Tools: `ask_peer_agent` (blocking), `submit_to_peer_agent` /
`poll_peer_agent` (async pair). See `server.py` for the tool contract.

Companion VS Code extension: `vscode-agent-bridge/` at the repo root (not
this directory).

## Setup (fresh clone)

### 1. Prerequisites

| Requirement | Check |
|---|---|
| Python ≥ 3.10 | `python3 --version` |
| [uv](https://docs.astral.sh/uv/getting-started/) | `uv --version` |
| Node.js + npm (extension build) | `npm --version` |
| VS Code CLI in PATH | `code --version` |
| cline-sr extension installed in VS Code | VS Code → Extensions → search "cline-sr" |

cline-sr must have **Hooks enabled** (the default). Verify in cline-sr's
settings webview, or check `~/.cline-sr/data/globalState.json` — the
`hooksEnabled` key must be `true` or absent.

If `code` is not in PATH on macOS:

```sh
export PATH="/Applications/Visual Studio Code.app/Contents/Resources/app/bin:$PATH"
```

### 2. Install the MCP server

```sh
cd mcp/vscode-agent-bridge
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/pytest          # optional: run the test suite
```

### 3. Install the companion extension

```sh
cd ../../vscode-agent-bridge   # repo root, not this directory
npm install
npm run compile
npm run install-dev            # symlinks into ~/.vscode/extensions/
```

Reload any VS Code window (Cmd+Shift+P → "Reload Window"), then confirm the
hook scripts were installed:

```sh
ls ~/Documents/Cline/Hooks/
# TaskStart PreToolUse PostToolUse TaskComplete TaskCancel
```

### 4. Register with Claude Code

```sh
claude mcp add vscode-agent-bridge -- \
  uv run --directory /path/to/skills-dev/mcp/vscode-agent-bridge vscode-agent-bridge
```

Or edit `~/.claude.json` directly:

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
      ]
    }
  }
}
```

Restart Claude Code so the server launches.

Optional environment variables (set in the `env` block of the registration):

| Variable | Default | Effect |
|---|---|---|
| `BRIDGE_ASK_TIMEOUT` | 180 | Blocking `ask_peer_agent` deadline (seconds) |
| `BRIDGE_ASYNC_TIMEOUT` | 1800 | `submit_to_peer_agent` expiry (seconds) |

### 5. Verify the integration

From the command line:

```sh
claude mcp list                # server should be listed and connected
tail -f ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log
```

From a Claude Code session: the tools `ask_peer_agent`,
`submit_to_peer_agent`, `poll_peer_agent`, `close_peer_agent`, and
`get_logs_for_session` should be available. Smoke test with a trivial
delegation (via the `delegate-to-cline` skill or the `cline` agent type) —
a dedicated VS Code window spawns at `~/.vscode-agent-bridge/data/` and the
session log shows the task lifecycle.

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Bridge window doesn't spawn | `code` CLI not in PATH (see step 1) |
| Blocking error notification in bridge window | Hooks disabled in cline-sr — toggle Hooks ON in its settings webview |
| Hook scripts missing | Extension not activated — reload a VS Code window after `npm run install-dev` |
| `ask_peer_agent` times out at 180 s | Use the async pair (`submit_to_peer_agent` + `poll_peer_agent`) for long tasks |
| Server crashes on startup | Dependencies missing — re-run `uv pip install -e ".[dev]"` |

## Dev

```
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/pytest
```
