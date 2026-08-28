"""Cline bridge MCP server — one tool, `ask_peer_model` (ADR-0070).

Environment variables:
    CLINE_BRIDGE_DIR: queue root (default: ~/.cline-bridge)
    CLINE_BRIDGE_TIMEOUT: seconds to block waiting for an answer (default: 180)
"""

from __future__ import annotations

import asyncio
import os
import time

from mcp.server.mcpserver import MCPServer

from bridge.queue import BridgeQueue

POLL_INTERVAL = 0.25

mcp = MCPServer("cline-bridge")


def _timeout() -> float:
    return float(os.getenv("CLINE_BRIDGE_TIMEOUT", "180"))


@mcp.tool()
async def ask_peer_model(question: str) -> dict:
    """Ask a different LLM a question and wait for its answer.

    Reaches a separate model running in another agent session, unreachable by any API key
    from this side. That model has bash only — no access to this repository, no tools, and
    no way to look anything up — so the question must carry every piece of context it needs.

    Blocks for up to 180 seconds and costs a full turn on the far side. Expensive: use it
    for a second opinion or a judgement only that model can give, never for trivia.

    Returns {id, status, answer, reason}. `status` is "answered" or "failed"; on failure
    `reason` is one of timeout, worker_offline, queue_unavailable.
    """
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")

    queue = BridgeQueue()
    try:
        queue.gc()
        if not queue.worker_alive():
            return {"id": None, "status": "failed", "answer": None, "reason": "worker_offline"}
        record = queue.submit(question)
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
