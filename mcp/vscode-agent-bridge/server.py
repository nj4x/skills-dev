"""vscode-agent-bridge MCP server — ask_peer_agent / submit_to_peer_agent / poll_peer_agent.

Delegates a task to cline-sr (a separate VS Code process) via a persistent
dedicated window. Submission rides a WebSocket the companion extension
holds open; lifecycle (start, tool use, completion, cancel) arrives over
HTTP from cline-sr's hook scripts, which inherit BRIDGE_PORT from this
server's own spawn of `code`.

Environment variables:
    BRIDGE_ASK_TIMEOUT: seconds `ask_peer_agent` blocks waiting for an answer (default: 180)
    BRIDGE_ASYNC_TIMEOUT: seconds before an unanswered submitted request expires (default: 1800)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from mcp.server.mcpserver.server import MCPServer
from mcp.server.mcpserver.context import Context

from bridge.bridge import Bridge
from bridge.logsetup import get_logger, setup_logging

setup_logging()
logger = get_logger("server")


@asynccontextmanager
async def lifespan(_server: MCPServer):
    bridge = Bridge()
    await bridge.start()
    try:
        yield bridge
    finally:
        await bridge.stop()


mcp = MCPServer("vscode-agent-bridge", lifespan=lifespan)


def _bridge(ctx: Context) -> Bridge:
    bridge = ctx.request_context.lifespan_context
    if not isinstance(bridge, Bridge):
        raise RuntimeError(f"lifespan_context not a Bridge: {type(bridge)}")
    return bridge


@mcp.tool()
async def ask_peer_agent(question: str, workspace: str, ctx: Context) -> dict:
    """Ask cline-sr, a separate VS Code agent, a question and wait for its answer.

    Reaches a dedicated VS Code window running cline-sr. It works as a
    delegate, not a sandbox: `workspace` (required, an existing directory) is
    the live working tree it reads and edits — uncommitted work included —
    so its edits land in your tree and show up in `git diff`. Never delegate
    a workspace holding production credentials: reads inside it are
    unconstrained.

    Blocks for up to 180 seconds and costs a full turn on the far side.
    Expensive: use it for a second opinion or a judgement only that agent can
    give, never for trivia.

    Returns {id, status, answer, command, reason}. `status` is "answered" or
    "failed"; on failure `reason` is one of timeout, instance_down,
    unknown_handle, internal_error.
    """
    return await _bridge(ctx).ask(question, workspace)


@mcp.tool()
async def submit_to_peer_agent(question: str, workspace: str, ctx: Context) -> dict:
    """Ask cline-sr a question without waiting for the answer.

    Same peer agent and same trust boundary as `ask_peer_agent` — see its
    docstring for what the far side can read and write. This variant returns
    at once, so use it for work measured in minutes: collect the answer later
    with `poll_peer_agent`. Submit several questions before polling any —
    each waits its turn behind whatever is already in flight.

    Returns {handle, status, reason}. `status` is always "submitted"; keep
    the `handle` to poll. A request nobody answers within 30 minutes expires,
    and polling it then reports failed with reason timeout.
    """
    return await _bridge(ctx).submit(question, workspace)


@mcp.tool()
async def poll_peer_agent(handle: str, ctx: Context) -> dict:
    """Check whether cline-sr has answered a submitted question. Never blocks.

    `handle` is what `submit_to_peer_agent` returned, or the `id` from an
    `ask_peer_agent` call that timed out — recovering an answer that arrived
    just too late.

    Returns {status, answer, command, reason, tool_uses, last_event_at}.
    `status` is "pending" (still queued or being worked on — `tool_uses` and
    `last_event_at`, sourced from cline-sr's tool-use hooks, distinguish
    actively working from hung), "answered", or "failed". On failure `reason`
    is timeout, instance_down, cancelled, unknown_handle, or internal_error.
    """
    return _bridge(ctx).poll(handle)


@mcp.tool()
async def close_peer_agent(ctx: Context) -> dict:
    """Close the dedicated cline-sr window and terminate the bridge session.

    Refuses if a task is in flight or queued. Caller must poll to completion
    before closing. Returns {status: "closed"} on success or {status: "busy"}
    if the queue is not empty.
    """
    return _bridge(ctx).close()


@mcp.tool()
async def get_logs_for_session(ctx: Context, handle: str | None = None) -> dict:
    """Get file paths and grep hints for logs related to current bridge session, tasks, and VS Code.

    Returns references to all logs generated in the current bridge process lifetime,
    allowing you to inspect what happened during task execution.

    Args:
        handle: optional task_id to filter to a single task's logs.
                if None, returns references for all tasks in the current session.

    Returns dict with keys:
        - status: "ok" or "unknown_handle"
        - session_log: path to ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log
                       grep with "task_id=<task_id>" to filter to a single task
        - tasks: list of {id, grep_hint, status} for each task (or just the specified handle)
        - vscode_exthost_log: path to latest ~/.vscode-agent-bridge/data/logs/<timestamp>/,
                              or null if VS Code has not been spawned yet

    Example:
        Get all logs in the session:
            result = await get_logs_for_session()
            # result["session_log"] = "~/.vscode-agent-bridge/logs/vscode-agent-bridge.log"
            # result["tasks"][0] = {id: "abc-123", grep_hint: "task_id=abc-123", status: "answered"}
            # Run: rg "task_id=abc-123" ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log

        Get logs for a single task:
            result = await get_logs_for_session(handle="abc-123")
    """
    return _bridge(ctx).get_logs_for_session(handle)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
