---
name: delegate-to-cline
description: Ask cline-sr, a separate VS Code agent, a question and return its answer inline. Use when the user wants a second opinion from cline, asks to "ask cline" or "delegate to cline", or a judgement call warrants an independent agent's read.
argument-hint: <question> [workspace]
---

# Delegate to cline-sr

Send one question to **cline-sr** through the vscode-agent-bridge MCP tools and relay the answer inline. This is the light path — for a long task (minutes of work, multi-step edits), dispatch the `cline` agent type instead (`Agent` tool, `subagent_type: "cline"`), which absorbs the wait and polling in a subagent.

## Procedure

1. Resolve the **workspace**: the directory the question is about, defaulting to the current working directory. It is cline-sr's live working tree — edits land there.
2. Call `ask_peer_agent` with the question and workspace. It blocks up to 180 seconds.
3. - `answered`: relay `answer` verbatim, plus `command` if non-null.
   - `failed` with reason `timeout`: the answer may still be coming — call `poll_peer_agent` with the returned `id` after a short wait to recover it. If still pending, hand the user the `id` and offer to poll again or re-dispatch as a `cline` subagent.
   - other failures: report the `reason` (`instance_down`, `cancelled`, `internal_error`) as-is.

The first call spawns the dedicated VS Code window if it is not already up — expect extra latency on a cold start.
