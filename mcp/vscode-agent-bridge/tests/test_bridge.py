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


async def test_get_logs_for_session_all_tasks(wired):
    """get_logs_for_session with no handle returns all tasks."""
    bridge, _ws = wired
    r1 = bridge.queue.submit("q1", "/tmp")
    r2 = bridge.queue.submit("q2", "/tmp")

    result = bridge.get_logs_for_session()

    assert result["status"] == "ok"
    assert "session_log" in result
    assert len(result["tasks"]) == 2
    assert {t["id"] for t in result["tasks"]} == {r1.id, r2.id}
    assert all(t["grep_hint"].startswith("task_id=") for t in result["tasks"])


async def test_get_logs_for_session_single_handle(wired):
    """get_logs_for_session with a handle returns only that task."""
    bridge, _ws = wired
    r1 = bridge.queue.submit("q1", "/tmp")
    r2 = bridge.queue.submit("q2", "/tmp")

    result = bridge.get_logs_for_session(handle=r1.id)

    assert result["status"] == "ok"
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["id"] == r1.id


async def test_get_logs_for_session_unknown_handle(wired):
    """get_logs_for_session with unknown handle returns error."""
    bridge, _ws = wired

    result = bridge.get_logs_for_session(handle="nonexistent")

    assert result["status"] == "unknown_handle"
    assert result["handle"] == "nonexistent"


def test_latest_vscode_exthost_dir_not_exist(monkeypatch, tmp_path):
    """_latest_vscode_exthost_dir returns None when logs dir doesn't exist."""
    bridge = Bridge()
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    result = bridge._latest_vscode_exthost_dir()
    assert result is None


def test_latest_vscode_exthost_dir_empty(tmp_path, monkeypatch):
    """_latest_vscode_exthost_dir returns None when logs dir is empty."""
    bridge = Bridge()
    data_dir = tmp_path / ".vscode-agent-bridge" / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    result = bridge._latest_vscode_exthost_dir()
    assert result is None


def test_latest_vscode_exthost_dir_picks_latest(tmp_path, monkeypatch):
    """_latest_vscode_exthost_dir returns the lexicographically latest dir."""
    bridge = Bridge()
    logs_dir = tmp_path / ".vscode-agent-bridge" / "data" / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "20260829T100000").mkdir()
    (logs_dir / "20260829T110000").mkdir()
    (logs_dir / "20260829T090000").mkdir()

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    result = bridge._latest_vscode_exthost_dir()
    assert result == str(logs_dir / "20260829T110000")
