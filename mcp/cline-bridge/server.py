"""Cline bridge MCP server — one tool, `ask_peer_model` (ADR-0070).

Environment variables:
    CLINE_BRIDGE_DIR: queue root (default: ~/.cline-bridge)
    CLINE_BRIDGE_TIMEOUT: seconds to block waiting for an answer (default: 180)
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from bridge.queue import BridgeQueue

POLL_INTERVAL = 0.25

mcp = MCPServer("cline-bridge")


def _timeout() -> float:
    return float(os.getenv("CLINE_BRIDGE_TIMEOUT", "180"))


@mcp.tool()
async def ask_peer_model(question: str, repo_path: str) -> dict:
    """Ask a different LLM a question and wait for its answer.

    Reaches a separate model running in another agent session, unreachable by any API key
    from this side. It works as a delegate, not a sandbox: `repo_path` (required, an existing
    directory) is the live working tree it reads and edits — uncommitted work included — so
    its edits land in your tree and show up in `git diff`. It writes nothing outside
    `repo_path`, and nothing under `.git/`, `.env*`, or build directories. It also has bash
    across the whole machine, but no skills, no MCP tools, no credentials, and no memory of
    this conversation, so inline anything it cannot reach on disk.

    Do not delegate a repo holding production credentials: reads inside `repo_path` are
    unconstrained, and the rule against reporting secrets is prompt guidance, not enforcement.

    Blocks for up to 180 seconds and costs a full turn on the far side. Expensive: use it
    for a second opinion or a judgement only that model can give, never for trivia.

    Returns {id, status, answer, reason}. `status` is "answered" or "failed"; on failure
    `reason` is one of timeout, worker_offline, queue_unavailable. `worker_offline` means no
    worker in the pool is alive, not that one of them died; it also carries `watchdog`:
    "alive" means a restart is coming, "offline" means nothing will restart the pool until a
    human does.
    """
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    if not Path(repo_path).is_dir():
        raise ValueError(f"repo_path is not an existing directory: {repo_path}")

    queue = BridgeQueue()
    try:
        queue.gc()
        if not queue.pool_alive():
            return {
                "id": None,
                "status": "failed",
                "answer": None,
                "reason": "worker_offline",
                "watchdog": "alive" if queue.watchdog_alive() else "offline",
            }
        record = queue.submit(question, repo_path)
    except OSError:
        return {"id": None, "status": "failed", "answer": None, "reason": "queue_unavailable"}

    deadline = time.monotonic() + _timeout()
    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        answered = queue.read_answered(record["id"])
        if answered is not None:
            return {"id": record["id"], "status": "answered", "answer": answered["answer"], "reason": None}

    queue.fail(record["id"])
    return {"id": record["id"], "status": "failed", "answer": None, "reason": "timeout"}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
