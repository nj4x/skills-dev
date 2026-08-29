"""Single orchestration object per MCP server process (ADR-0068).

Wraps BridgeQueue, InstanceManager, and HookServer. Exposed via MCPServer's
lifespan context so tool functions and tests depend on one interface instead of
three module globals.
"""

from __future__ import annotations

import asyncio

from bridge.hookserver import HookServer
from bridge.instance import InstanceManager
from bridge.queue import BridgeQueue

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
        """Dispatch the next queued record, if the window is free to take one."""
        record = self.queue.next_dispatchable()
        if record is None:
            return
        try:
            await self.instance.ensure_ready(record.workspace, self.hooks.port)
            await self.hooks.dispatch(record.question)
        except Exception:
            from bridge.instance import InstanceUnreachable
            self.queue.fail(record.id, "instance_down")
            await self._pump(async_timeout)

    async def _sweep_loop(self, async_timeout: float = 1800.0) -> None:
        """Run the expiration sweep at regular intervals."""
        try:
            while True:
                await asyncio.sleep(SWEEP_INTERVAL)
                self.queue.sweep_expired(async_timeout)
                await self._pump(async_timeout)
        except asyncio.CancelledError:
            pass
