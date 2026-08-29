"""Two-channel transport on $BRIDGE_PORT (design/70).

HTTP `/hook` receives fire-and-forget lifecycle POSTs from cline-sr's hook
scripts (TaskStart/PreToolUse/PostToolUse/TaskComplete/TaskCancel). The
WebSocket `/ws` is held open by the companion extension for the window's
lifetime: its connection is the liveness signal, and task submission rides
the same socket (the extension calls cline-sr's URI handler in-process).

Only one task runs at a time, so a hook POST is never disambiguated by a
request id — whichever record the queue holds in flight is the one it's
about.
"""

from __future__ import annotations

from aiohttp import WSMsgType, web

from bridge.instance import InstanceManager, InstanceUnreachable
from bridge.queue import BridgeQueue


class HookServer:
    def __init__(self, queue: BridgeQueue, instance: InstanceManager) -> None:
        self._queue = queue
        self._instance = instance
        self._ws: web.WebSocketResponse | None = None
        self._runner: web.AppRunner | None = None
        self.port: int | None = None

        self.app = web.Application()
        self.app.add_routes(
            [
                web.post("/hook", self._handle_hook),
                web.get("/ws", self._handle_ws),
            ]
        )

    async def start(self, host: str = "127.0.0.1") -> int:
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def dispatch(self, prompt: str) -> None:
        if self._ws is None:
            raise InstanceUnreachable("no connected extension to dispatch to")
        await self._ws.send_json({"type": "submit", "prompt": prompt})

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=15)
        await ws.prepare(request)
        self._ws = ws
        self._instance.mark_connected()
        try:
            async for msg in ws:
                if msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSING):
                    break
        finally:
            self._instance.mark_disconnected()
            self._queue.fail_in_flight("instance_down")
            if self._ws is ws:
                self._ws = None
        return ws

    async def _handle_hook(self, request: web.Request) -> web.Response:
        payload = await request.json()
        hook_name = payload.get("hookName")

        if hook_name in ("PreToolUse", "PostToolUse"):
            self._queue.record_tool_use()
        elif hook_name == "TaskComplete":
            meta = payload.get("taskComplete", {}).get("taskMetadata", {})
            self._queue.complete(meta.get("result", ""), meta.get("command"))
        elif hook_name == "TaskCancel":
            self._queue.cancel("cancelled")
        # TaskStart, TaskResume, UserPromptSubmit: no-op — dispatch already marked the record.

        return web.json_response({"ok": True})
