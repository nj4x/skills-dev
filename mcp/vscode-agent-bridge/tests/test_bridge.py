import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.bridge import Bridge
from bridge.logsetup import task_id_var


@pytest.fixture
async def wired(monkeypatch):
    bridge = Bridge()

    async def fake_ensure_ready(workspace, port):
        bridge.instance.workspace = workspace
        bridge.instance.mark_connected()

    monkeypatch.setattr(bridge.instance, "ensure_ready", fake_ensure_ready)

    async with TestClient(TestServer(bridge.hooks.app)) as client:
        ws = await client.ws_connect("/ws")
        await asyncio.sleep(0)
        yield bridge, ws
        if not ws.closed:
            await ws.close()


async def test_pump_clears_task_id_after_dispatch(wired):
    """A persistent caller (the sweeper task) must not see a prior task's id
    bleed into the next _pump call's log context (ADR-0069)."""
    bridge, ws = wired
    record = bridge.queue.submit("q", "/tmp")

    await bridge._pump(1800.0)
    await ws.receive_json()  # drain the dispatch

    assert record.status == "dispatched"
    assert task_id_var.get() == ""


async def test_pump_clears_task_id_when_nothing_dispatchable(wired):
    bridge, _ws = wired
    task_id_var.set("stale-from-earlier-call")

    await bridge._pump(1800.0)

    assert task_id_var.get() == ""
