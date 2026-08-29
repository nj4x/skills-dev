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

## Dev

```
uv venv .venv
uv pip install -e ".[dev]"
.venv/bin/pytest
```
