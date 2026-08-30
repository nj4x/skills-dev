# vscode-agent-bridge (companion extension)

Companion VS Code extension for the `mcp/vscode-agent-bridge` MCP server.
Together they let Claude Code delegate tasks to cline-sr running in a
dedicated VS Code window (wayfinder map
[#67](https://github.com/nj4x/skills-dev/issues/67), designs
[#70](https://github.com/nj4x/skills-dev/issues/70) /
[#71](https://github.com/nj4x/skills-dev/issues/71)).

For end-to-end setup from a fresh clone (prerequisites, MCP server install,
Claude Code registration, verification), see
[`mcp/vscode-agent-bridge/README.md`](../mcp/vscode-agent-bridge/README.md).

## What it does

At `activate()` (every window, `onStartupFinished`):

1. **Installs hook scripts** — idempotently writes the five templates in
   `hooks/` (`TaskStart`, `PreToolUse`, `PostToolUse`, `TaskComplete`,
   `TaskCancel` — extensionless names, per cline-sr's hook convention) to
   `~/Documents/Cline/Hooks/` with mode `0755`. Skips when content already
   matches (sha256); rewrites stale bridge-owned scripts (identified by the
   `vscode-agent-bridge hook` marker line); never overwrites foreign scripts —
   warns instead.

Only in the dedicated bridge window (`BRIDGE_PORT` set in the environment by
the MCP server's spawn of `code`):

2. **Checks `hooksEnabled`** — reads `~/.cline-sr/data/globalState.json`
   (read-only). Absent key means enabled (cline-sr defaults it to true).
   If explicitly `false`, shows a blocking error notification: the user must
   toggle Hooks in cline-sr's settings webview (no programmatic API exists).
3. **Holds the liveness WebSocket** — connects to
   `ws://127.0.0.1:$BRIDGE_PORT/ws` and reconnects every 3 s while the window
   lives. The MCP server treats socket close as instance-down.
4. **Submits tasks** — on a `{"type": "submit", "prompt": ...}` frame it calls
   `vscode.env.openExternal(<uriScheme>://cline-sr.cline-sr/task?prompt=<encoded>)`,
   which activates cline-sr's URI handler in this window.

Hook scripts read `$BRIDGE_PORT` at runtime and POST their stdin JSON to the
MCP server's `/hook` endpoint. In windows without `BRIDGE_PORT` they no-op,
so the global install is safe for normal cline-sr use.

## Dev loop

```sh
npm install
npm run compile
npm run install-dev   # symlinks this directory into ~/.vscode/extensions/
```

Then reload the VS Code window. Rebuild + reload to iterate; no vsix pipeline.
