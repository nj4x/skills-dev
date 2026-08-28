"""Cline bridge MCP server — `ask_peer_model` (ADR-0070) and the async pair (ADR-0076).

Environment variables:
    CLINE_BRIDGE_DIR: queue root (default: ~/.cline-bridge)
    CLINE_BRIDGE_TIMEOUT: seconds `ask_peer_model` blocks waiting for an answer (default: 180)
    CLINE_BRIDGE_ASYNC_TIMEOUT: seconds before an unanswered request is swept (default: 1800)
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


def _validate(question: str, repo_path: str) -> str:
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    if not Path(repo_path).is_dir():
        raise ValueError(f"repo_path is not an existing directory: {repo_path}")
    return question


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
    question = _validate(question, repo_path)

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

    queue.fail(record["id"], reason="timeout")
    return {"id": record["id"], "status": "failed", "answer": None, "reason": "timeout"}


@mcp.tool()
async def submit_to_peer_model(question: str, repo_path: str, thread_id: str | None = None) -> dict:
    """Ask a different LLM a question without waiting for the answer.

    Same peer model and same trust boundary as `ask_peer_model` — see its docstring for what
    the far side can read and write, and for what is unsafe to delegate. This variant returns
    at once, so use it for work measured in minutes: you collect the answer later with
    `poll_peer_model`. Submit several questions before polling any of them if you like.

    Pass `thread_id` (any string you choose) to keep a follow-up in the same worker session,
    which preserves the context of earlier questions in that thread. Submit serially within a
    thread: wait for one message to be answered before sending the next, or the follow-up is
    not reachable by a threaded poll. Every message in a thread must use the same `repo_path`
    as the first one.

    Returns {handle, status, reason}. `status` is "submitted" or "failed"; on failure `handle`
    is None and `reason` is queue_unavailable or repo_path_mismatch. Keep the handle and the
    `thread_id` you used — you need both to poll. A request nobody answers within 30 minutes
    expires, and polling it then reports failed.
    """
    question = _validate(question, repo_path)

    queue = BridgeQueue()
    try:
        queue.gc()
        record = queue.submit(question, repo_path, thread_id)
    except ValueError:
        return {"handle": None, "status": "failed", "reason": "repo_path_mismatch"}
    except OSError:
        return {"handle": None, "status": "failed", "reason": "queue_unavailable"}
    return {"handle": record["id"], "status": "submitted", "reason": None}


@mcp.tool()
async def poll_peer_model(handle: str, thread_id: str | None = None) -> dict:
    """Check whether the peer model has answered a submitted question. Never blocks.

    `handle` is what `submit_to_peer_model` returned, or the `id` from an `ask_peer_model`
    call — including one that timed out, which is how you recover an answer that arrived just
    too late. Pass the same `thread_id` you submitted with, or the handle will not be found.

    Returns {status, answer, reason}. `status` is "pending" (still queued or being worked on —
    check back later), "answered" (`answer` holds the text), or "failed". On failure `reason`
    is one of timeout (nobody answered within 30 minutes), unknown_handle (no such request:
    never submitted, expired past the 7-day history, or polled with the wrong `thread_id`), or
    internal_error. Treat any reason you do not recognise as terminal, not as pending.
    """
    queue = BridgeQueue()
    try:
        queue.gc()
        found = queue.read_record(handle, thread_id)
    except OSError:
        return {"status": "failed", "answer": None, "reason": "internal_error"}
    if found is None:
        return {"status": "failed", "answer": None, "reason": "unknown_handle"}

    state, record = found
    if state == "answered":
        return {"status": "answered", "answer": record["answer"], "reason": None}
    if state == "failed":
        return {"status": "failed", "answer": None, "reason": record.get("reason") or "internal_error"}
    return {"status": "pending", "answer": None, "reason": None}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
