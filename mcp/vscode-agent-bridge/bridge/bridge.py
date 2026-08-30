"""Single orchestration object per MCP server process (ADR-0068).

Wraps BridgeQueue, InstanceManager, and HookServer. Exposed via MCPServer's
lifespan context so tool functions and tests depend on one interface instead of
three module globals.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from bridge.hookserver import HookServer
from bridge.instance import InstanceManager
from bridge.logsetup import get_logger, set_task_id
from bridge.queue import BridgeQueue

logger = get_logger("bridge")

POLL_INTERVAL = 0.25
SWEEP_INTERVAL = 5.0


class Bridge:
    def __init__(self) -> None:
        self.queue = BridgeQueue()
        self.instance = InstanceManager()
        self.hooks = HookServer(self.queue, self.instance)
        self._sweeper_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the hook server and pump/sweep loop."""
        await self.hooks.start()
        self._sweeper_task = asyncio.create_task(self._sweep_loop())

    async def stop(self) -> None:
        """Stop the sweeper and hook server."""
        if self._sweeper_task is not None:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
        await self.hooks.stop()

    async def _pump(self, async_timeout: float) -> None:
        """Dispatch the next queued record, if the window is free to take one.

        `set_task_id` writes to the calling asyncio Task's context. The
        sweeper drives this from one long-lived Task (_sweep_loop), so the id
        must be cleared here rather than left to bleed into the next
        iteration's log lines.
        """
        set_task_id(None)
        logger.info("_pump: enter")
        record = self.queue.next_dispatchable()
        if record is None:
            logger.info("_pump: exit (nothing dispatchable)")
            return
        set_task_id(record.id)
        try:
            await self.instance.ensure_ready(record.workspace, self.hooks.port)
            await self.hooks.dispatch(record.question)
        except Exception:
            logger.exception("dispatch of task %s failed", record.id)
            self.queue.fail(record.id, "instance_down")
            set_task_id(None)
            await self._pump(async_timeout)
            return
        logger.info("_pump: exit")
        set_task_id(None)

    async def _sweep_loop(self, async_timeout: float = 1800.0) -> None:
        """Run the expiration sweep at regular intervals."""
        try:
            while True:
                await asyncio.sleep(SWEEP_INTERVAL)
                logger.debug("sweep_expired: run")
                self.queue.sweep_expired(async_timeout)
                await self._pump(async_timeout)
        except asyncio.CancelledError:
            pass

    def get_logs_for_session(self, handle: str | None = None) -> dict:
        """Return file paths and grep hints for logs in current bridge session.

        Args:
            handle: optional task_id to filter logs to a single task.
                    if None, returns references for all tasks + session log.

        Returns dict with keys:
            - session_log: path to ~/.vscode-agent-bridge/logs/vscode-agent-bridge.log
            - tasks: list of dicts, one per task (or per handle if specified).
                     each dict has: {id, grep_hint, status}
            - vscode_exthost_log: path to latest ~/.vscode-agent-bridge/data/logs/*/
                                  or None if dir doesn't exist yet.

        If handle is provided but not found in queue, returns {status: "unknown_handle"}.
        """
        session_log = Path.home() / ".vscode-agent-bridge" / "logs" / "vscode-agent-bridge.log"

        if handle is not None:
            record = self.queue.get(handle)
            if record is None:
                return {"status": "unknown_handle", "handle": handle}
            tasks = [{"id": record.id, "grep_hint": f"task_id={record.id}", "status": record.status}]
        else:
            tasks = [
                {"id": r.id, "grep_hint": f"task_id={r.id}", "status": r.status}
                for r in self.queue._records.values()
            ]

        exthost_log = self._latest_vscode_exthost_dir()

        return {
            "status": "ok",
            "session_log": str(session_log),
            "tasks": tasks,
            "vscode_exthost_log": exthost_log,
        }

    def _latest_vscode_exthost_dir(self) -> str | None:
        """Return path to latest VS Code exthost log dir, or None if not found."""
        logs_dir = Path.home() / ".vscode-agent-bridge" / "data" / "logs"
        if not logs_dir.exists():
            return None
        try:
            dirs = sorted([d for d in logs_dir.iterdir() if d.is_dir()])
            if not dirs:
                return None
            return str(dirs[-1])
        except (OSError, RuntimeError):
            return None
