import asyncio

import pytest

from bridge.instance import InstanceManager, InstanceUnreachable, SPAWN_TIMEOUT


class FakeProcess:
    async def wait(self) -> int:
        return 0


@pytest.fixture
def fake_spawn(monkeypatch):
    calls: list[tuple[tuple, dict]] = []

    async def _create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _create_subprocess_exec)
    return calls


async def test_ensure_ready_spawns_without_reuse_window_when_dead(fake_spawn):
    manager = InstanceManager(code_bin="code")

    async def connect_soon():
        await asyncio.sleep(0)
        manager.mark_connected()

    task = asyncio.create_task(connect_soon())
    await manager.ensure_ready("/tmp/repo", port=4321)
    await task

    args, kwargs = fake_spawn[0]
    assert "--reuse-window" not in args
    assert args[-1] == "/tmp/repo"
    assert kwargs["env"]["BRIDGE_PORT"] == "4321"
    assert manager.workspace == "/tmp/repo"
    assert manager.alive


async def test_ensure_ready_skips_spawn_when_already_open(fake_spawn):
    manager = InstanceManager()
    manager._alive = True
    manager.workspace = "/tmp/repo"
    manager._connected.set()

    await manager.ensure_ready("/tmp/repo", port=4321)
    assert fake_spawn == []


async def test_ensure_ready_reuses_window_on_workspace_switch(fake_spawn):
    manager = InstanceManager()
    manager._alive = True
    manager.workspace = "/tmp/old"
    manager._connected.set()

    async def connect_soon():
        await asyncio.sleep(0)
        manager.mark_connected()

    task = asyncio.create_task(connect_soon())
    await manager.ensure_ready("/tmp/new", port=4321)
    await task

    args, _ = fake_spawn[0]
    assert "--reuse-window" in args
    assert args[-1] == "/tmp/new"
    assert manager.workspace == "/tmp/new"


async def test_ensure_ready_times_out_if_extension_never_connects(fake_spawn, monkeypatch):
    monkeypatch.setattr("bridge.instance.SPAWN_TIMEOUT", 0.01)
    manager = InstanceManager()
    with pytest.raises(InstanceUnreachable):
        await manager.ensure_ready("/tmp/repo", port=4321)
    assert not manager.alive


def test_mark_disconnected_clears_alive():
    manager = InstanceManager()
    manager.mark_connected()
    assert manager.alive
    manager.mark_disconnected()
    assert not manager.alive
