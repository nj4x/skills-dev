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

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from bridge.hookserver import HookServer
from bridge.instance import InstanceManager, InstanceUnreachable
from bridge.queue import BridgeQueue

POLL_INTERVAL = 0.25
SWEEP_INTERVAL = 5.0

queue = BridgeQueue()
instance = InstanceManager()
hooks = HookServer(queue, instance)


def _ask_timeout() -> float:
    return float(os.getenv("BRIDGE_ASK_TIMEOUT", "180"))


def _async_timeout() -> float:
    return float(os.getenv("BRIDGE_ASYNC_TIMEOUT", "1800"))


def _validate(question: str, workspace: str) -> str:
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    if not Path(workspace).is_dir():
        raise ValueError(f"workspace is not an existing directory: {workspace}")
    return question


async def _pump() -> None:
    """Dispatch the next queued record, if the window is free to take one."""
    record = queue.next_dispatchable()
    if record is None:
        return
    try:
        await instance.ensure_ready(record.workspace, hooks.port)
        await hooks.dispatch(record.question)
    except (InstanceUnreachable, OSError):
        queue.fail(record.id, "instance_down")
        await _pump()


async def _sweeper() -> None:
    while True:
        await asyncio.sleep(SWEEP_INTERVAL)
        queue.sweep_expired(_async_timeout())
        await _pump()


@asynccontextmanager
async def lifespan(_server: MCPServer):
    await hooks.start()
    task = asyncio.create_task(_sweeper())
    try:
        yield {}
    finally:
        task.cancel()
        await hooks.stop()


mcp = MCPServer("vscode-agent-bridge", lifespan=lifespan)


@mcp.tool()
async def ask_peer_agent(question: str, workspace: str) -> dict:
    """Ask cline-sr, a separate VS Code agent, a question and wait for its answer.

    Reaches a dedicated VS Code window running cline-sr, unreachable by any API
    key from this side. It works as a delegate, not a sandbox: `workspace`
    (required, an existing directory) is the live working tree it reads and
    edits — uncommitted work included — so its edits land in your tree and
    show up in `git diff`. Never delegate a workspace holding production
    credentials: reads inside it are unconstrained.

    Blocks for up to 180 seconds and costs a full turn on the far side.
    Expensive: use it for a second opinion or a judgement only that agent can
    give, never for trivia.

    Returns {id, status, answer, command, reason}. `status` is "answered" or
    "failed"; on failure `reason` is one of timeout, instance_down,
    unknown_handle, internal_error.
    """
    question = _validate(question, workspace)
    record = queue.submit(question, workspace)
    await _pump()

    loop = asyncio.get_event_loop()
    deadline = loop.time() + _ask_timeout()
    while True:
        current = queue.get(record.id)
        if current.status == "answered":
            return {"id": record.id, "status": "answered", "answer": current.answer, "command": current.command, "reason": None}
        if current.status == "failed":
            return {"id": record.id, "status": "failed", "answer": None, "command": None, "reason": current.reason}
        remaining = deadline - loop.time()
        if remaining <= 0:
            queue.fail(record.id, "timeout")
            return {"id": record.id, "status": "failed", "answer": None, "command": None, "reason": "timeout"}
        await asyncio.sleep(min(POLL_INTERVAL, remaining))


@mcp.tool()
async def submit_to_peer_agent(question: str, workspace: str) -> dict:
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
    question = _validate(question, workspace)
    record = queue.submit(question, workspace)
    await _pump()
    return {"handle": record.id, "status": "submitted", "reason": None}


@mcp.tool()
async def poll_peer_agent(handle: str) -> dict:
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
    record = queue.get(handle)
    if record is None:
        return {"status": "failed", "answer": None, "command": None, "reason": "unknown_handle", "tool_uses": None, "last_event_at": None}
    if record.status == "answered":
        return {"status": "answered", "answer": record.answer, "command": record.command, "reason": None, "tool_uses": record.tool_uses, "last_event_at": record.last_event_at}
    if record.status == "failed":
        return {"status": "failed", "answer": None, "command": None, "reason": record.reason, "tool_uses": record.tool_uses, "last_event_at": record.last_event_at}
    return {"status": "pending", "answer": None, "command": None, "reason": None, "tool_uses": record.tool_uses, "last_event_at": record.last_event_at}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
