---
slug: ask-peer-model
title: ⚠️ DEPRECATED — Consult a second LLM through cline-bridge
remarks: Deprecated 2026-08-28. Use vscode-agent-bridge instead.
---

# ⚠️ DEPRECATED: ask-peer-model

**Status:** Superseded by `vscode-agent-bridge`.

## What changed

The original `cline-bridge` MCP server used a filesystem queue + bash polling — fundamentally unreliable for control flow. The replacement (`vscode-agent-bridge`) uses cline-sr's hook system (synchronous, deterministic, direct HTTP callbacks) for lifecycle events and a WebSocket dispatch channel, eliminating polling entirely.

**Proof of replacement:** End-to-end round-trip verified in [map #67, ticket #76](https://github.com/nj4x/skills-dev/issues/76). ADRs 0078–0079 (cline-bridge) superseded.

## Migration

If your skills or code call `ask_peer_model` / `submit_to_peer_model` / `poll_peer_model`:

1. Install `vscode-agent-bridge` (from the top-level `vscode-agent-bridge/` directory).
2. Replace tool names: `ask_peer_model` → `ask_peer_agent`; `submit_to_peer_model` → `submit_to_peer_agent`; `poll_peer_model` → `poll_peer_agent`.
3. Parameters are identical; return shape is the same. No filesystem queue to manage.

## See Also

- Map #67: [wayfinder: Claude Code to cline-sr bridge via VS Code companion extension](https://github.com/nj4x/skills-dev/issues/67)
- Map #37/#52: [cline-bridge origin & prior art](https://github.com/nj4x/skills-dev/issues/37)
- Ticket #73: [task: retire cline-bridge (map #37/#52)](https://github.com/nj4x/skills-dev/issues/73)
