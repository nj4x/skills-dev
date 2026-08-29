# ADR manifest — vscode-agent-bridge observability

## Design Decisions Reached During Grilling

Decisions reached during a `/grilling` session on adding logging/observability to vscode-agent-bridge (MCP server + VS Code extension), triggered by a real incident: `poll_peer_agent` returned `{status: failed, reason: cancelled}` for a task the user believed had completed, with no log to check.

- docs/adr/0069-vscode-agent-bridge-observability.md
