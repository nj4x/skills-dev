import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bridge.hookserver import HookServer
from bridge.instance import InstanceManager, InstanceUnreachable
from bridge.queue import BridgeQueue


@pytest.fixture
async def wired():
    queue = BridgeQueue()
    instance = InstanceManager()
    server = HookServer(queue, instance)
    async with TestClient(TestServer(server.app)) as client:
        yield queue, instance, server, client


async def test_ws_connect_marks_instance_alive(wired):
    queue, instance, server, client = wired
    ws = await client.ws_connect("/ws")
    await asyncio.sleep(0)  # let the server-side handler run past `prepare`
    assert instance.alive
    await ws.close()


async def test_ws_disconnect_marks_instance_down_and_fails_in_flight(wired):
    queue, instance, server, client = wired
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()

    ws = await client.ws_connect("/ws")
    await ws.close()
    await client.server.close()  # ensure the server-side handler has unwound

    assert not instance.alive
    assert record.status == "failed"
    assert record.reason == "instance_down"


async def test_dispatch_without_connection_raises(wired):
    _, _, server, _ = wired
    with pytest.raises(InstanceUnreachable):
        await server.dispatch("do the thing")


async def test_dispatch_sends_submit_over_ws(wired):
    queue, instance, server, client = wired
    ws = await client.ws_connect("/ws")

    await server.dispatch("fix the bug")
    msg = await ws.receive_json()
    assert msg == {"type": "submit", "prompt": "fix the bug"}
    await ws.close()


async def test_hook_pre_post_tool_use_increments_in_flight(wired):
    queue, instance, server, client = wired
    queue.submit("q", "/tmp")
    queue.next_dispatchable()

    resp = await client.post("/hook", json={"hookName": "PreToolUse"})
    assert resp.status == 200
    resp = await client.post("/hook", json={"hookName": "PostToolUse"})
    assert resp.status == 200

    assert queue.in_flight().tool_uses == 2


async def test_hook_task_complete_resolves_in_flight(wired):
    queue, instance, server, client = wired
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()

    payload = {
        "hookName": "TaskComplete",
        "taskComplete": {"taskMetadata": {"result": "the answer", "command": "pytest"}},
    }
    resp = await client.post("/hook", json=payload)
    assert resp.status == 200
    assert record.status == "answered"
    assert record.answer == "the answer"
    assert record.command == "pytest"
    assert queue.in_flight() is None


async def test_hook_task_cancel_after_bind_fails_in_flight(wired):
    queue, instance, server, client = wired
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()

    await client.post("/hook", json={"hookName": "TaskStart", "taskStart": {"taskMetadata": {"taskId": "ct-1"}}})
    resp = await client.post("/hook", json={"hookName": "TaskCancel", "taskCancel": {"taskMetadata": {"taskId": "ct-1"}}})
    assert resp.status == 200
    assert record.status == "failed"
    assert record.reason == "cancelled"


async def test_hook_task_start_binds_cline_task_id(wired):
    queue, instance, server, client = wired
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()

    resp = await client.post("/hook", json={"hookName": "TaskStart", "taskStart": {"taskMetadata": {"taskId": "ct-1"}}})
    assert resp.status == 200
    assert record.status == "dispatched"
    assert record.cline_task_id == "ct-1"


async def test_spurious_teardown_cancel_race_is_survived(wired):
    """Reproduces the ADR-0070 race: old task's TaskCancel ~150ms after dispatch."""
    queue, instance, server, client = wired
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()

    # cline-sr tears down its previous task before starting the new one
    resp = await client.post("/hook", json={"hookName": "TaskCancel", "taskCancel": {"taskMetadata": {"taskId": "old-task", "completionStatus": "abandoned"}}})
    assert resp.status == 200
    assert record.status == "dispatched"  # NOT failed

    # the real task then starts, works, and completes
    await client.post("/hook", json={"hookName": "TaskStart", "taskStart": {"taskMetadata": {"taskId": "new-task"}}})
    await client.post("/hook", json={"hookName": "PreToolUse", "preToolUse": {"toolName": "read_file"}})
    await client.post("/hook", json={"hookName": "PostToolUse", "postToolUse": {"toolName": "read_file"}})
    await client.post("/hook", json={
        "hookName": "TaskComplete",
        "taskComplete": {"taskMetadata": {"taskId": "new-task", "result": "the answer", "command": None}},
    })

    assert record.status == "answered"
    assert record.answer == "the answer"
    assert record.tool_uses == 2


async def test_late_completion_recovers_timed_out_record(wired):
    queue, instance, server, client = wired
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()

    await client.post("/hook", json={"hookName": "TaskStart", "taskStart": {"taskMetadata": {"taskId": "ct-1"}}})
    queue.fail(record.id, "timeout")  # ask deadline expired while cline-sr kept working
    assert record.status == "failed"

    await client.post("/hook", json={
        "hookName": "TaskComplete",
        "taskComplete": {"taskMetadata": {"taskId": "ct-1", "result": "late answer"}},
    })
    assert record.status == "answered"
    assert record.answer == "late answer"
