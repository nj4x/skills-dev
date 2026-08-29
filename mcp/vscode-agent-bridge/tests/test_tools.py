import asyncio

import pytest
from aiohttp.test_utils import TestClient, TestServer

import server as srv


@pytest.fixture(autouse=True)
async def fresh_state(monkeypatch, tmp_path):
    """Give every test its own queue/instance/hookserver, wired the way
    lifespan() would, but backed by aiohttp's TestClient instead of a real
    TCP bind, and a stub instance spawn instead of a real `code` process."""
    from bridge.hookserver import HookServer
    from bridge.instance import InstanceManager
    from bridge.queue import BridgeQueue

    queue = BridgeQueue()
    instance = InstanceManager()
    hooks = HookServer(queue, instance)

    async def fake_ensure_ready(workspace, port):
        instance.workspace = workspace
        instance.mark_connected()

    monkeypatch.setattr(instance, "ensure_ready", fake_ensure_ready)
    monkeypatch.setattr(srv, "queue", queue)
    monkeypatch.setattr(srv, "instance", instance)
    monkeypatch.setattr(srv, "hooks", hooks)

    async with TestClient(TestServer(hooks.app)) as client:
        ws = await client.ws_connect("/ws")
        await asyncio.sleep(0)
        yield queue, instance, hooks, ws, tmp_path
        if not ws.closed:
            await ws.close()


async def _drain_submit(ws) -> dict:
    return await ws.receive_json()


async def test_submit_then_answer_via_hook_resolves_ask(fresh_state):
    queue, instance, hooks, ws, tmp_path = fresh_state

    ask_task = asyncio.create_task(srv.ask_peer_agent("what is x", str(tmp_path)))
    submitted = await _drain_submit(ws)
    assert submitted == {"type": "submit", "prompt": "what is x"}

    # simulate cline-sr's TaskComplete hook resolving the in-flight record
    # (the hook POST -> queue.complete wiring itself is covered by test_hookserver.py)
    queue.complete("x is 42", None)

    result = await ask_task
    assert result["status"] == "answered"
    assert result["answer"] == "x is 42"
    assert result["reason"] is None


async def test_submit_to_peer_agent_returns_handle_immediately(fresh_state):
    queue, instance, hooks, ws, tmp_path = fresh_state

    result = await srv.submit_to_peer_agent("do a thing", str(tmp_path))
    assert result["status"] == "submitted"
    assert result["reason"] is None
    handle = result["handle"]

    submitted = await _drain_submit(ws)
    assert submitted["prompt"] == "do a thing"

    poll = await srv.poll_peer_agent(handle)
    assert poll["status"] == "pending"
    assert poll["tool_uses"] == 0


async def test_poll_unknown_handle(fresh_state):
    result = await srv.poll_peer_agent("does-not-exist")
    assert result == {
        "status": "failed",
        "answer": None,
        "command": None,
        "reason": "unknown_handle",
        "tool_uses": None,
        "last_event_at": None,
    }


async def test_second_submit_queues_behind_first(fresh_state):
    queue, instance, hooks, ws, tmp_path = fresh_state

    first = await srv.submit_to_peer_agent("q1", str(tmp_path))
    await _drain_submit(ws)  # first got dispatched

    second = await srv.submit_to_peer_agent("q2", str(tmp_path))
    poll_second = await srv.poll_peer_agent(second["handle"])
    assert poll_second["status"] == "pending"
    assert queue.get(second["handle"]).status == "queued"

    queue.complete("answer1", None)
    await srv._pump()
    dispatched_second = await _drain_submit(ws)
    assert dispatched_second["prompt"] == "q2"
    assert queue.get(second["handle"]).status == "dispatched"


async def test_ask_peer_agent_rejects_missing_workspace(fresh_state):
    with pytest.raises(ValueError):
        await srv.ask_peer_agent("q", "/definitely/not/a/real/dir")


async def test_ask_peer_agent_rejects_blank_question(fresh_state, tmp_path):
    with pytest.raises(ValueError):
        await srv.ask_peer_agent("   ", str(tmp_path))


async def test_ask_peer_agent_times_out(fresh_state, tmp_path, monkeypatch):
    monkeypatch.setenv("BRIDGE_ASK_TIMEOUT", "0.05")
    queue, instance, hooks, ws, tmp_path = fresh_state
    result = await srv.ask_peer_agent("never answered", str(tmp_path))
    assert result["status"] == "failed"
    assert result["reason"] == "timeout"


async def test_close_peer_agent_succeeds_when_idle(fresh_state):
    queue, instance, hooks, ws, tmp_path = fresh_state
    result = await srv.close_peer_agent()
    assert result == {"status": "closed"}
    assert not instance.alive


async def test_close_peer_agent_refuses_when_in_flight(fresh_state, tmp_path):
    queue, instance, hooks, ws, tmp_path = fresh_state
    await srv.submit_to_peer_agent("task", str(tmp_path))
    await _drain_submit(ws)

    result = await srv.close_peer_agent()
    assert result == {"status": "busy"}


async def test_close_peer_agent_refuses_when_queued(fresh_state, tmp_path):
    queue, instance, hooks, ws, tmp_path = fresh_state
    await srv.submit_to_peer_agent("task1", str(tmp_path))
    await _drain_submit(ws)

    # Submit second (stays queued)
    await srv.submit_to_peer_agent("task2", str(tmp_path))

    result = await srv.close_peer_agent()
    assert result == {"status": "busy"}
