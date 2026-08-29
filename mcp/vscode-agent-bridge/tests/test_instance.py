import asyncio
import json

import pytest

from bridge.instance import (
    SEED_SETTINGS,
    InstanceManager,
    InstanceUnreachable,
    SPAWN_TIMEOUT,
    _seed_settings,
)


class FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None

    async def wait(self) -> int:
        return 0

    def terminate(self) -> None:
        pass


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr("bridge.instance.DATA_DIR", data_dir)
    return data_dir


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


def test_seed_settings_creates_file_with_defaults(tmp_data_dir):
    _seed_settings()
    written = json.loads((tmp_data_dir / "User" / "settings.json").read_text())
    assert written == SEED_SETTINGS


def test_seed_settings_preserves_existing_overrides(tmp_data_dir):
    settings_path = tmp_data_dir / "User" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"update.mode": "manual", "editor.fontSize": 15}))

    _seed_settings()
    written = json.loads(settings_path.read_text())
    assert written["update.mode"] == "manual"
    assert written["editor.fontSize"] == 15
    assert written["security.workspace.trust.enabled"] is False


def test_seed_settings_leaves_unparsable_file_untouched(tmp_data_dir):
    settings_path = tmp_data_dir / "User" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{not json")

    _seed_settings()
    assert settings_path.read_text() == "{not json"


async def test_ensure_ready_seeds_settings_before_spawn(fake_spawn, tmp_data_dir):
    manager = InstanceManager()

    async def connect_soon():
        await asyncio.sleep(0)
        manager.mark_connected()

    task = asyncio.create_task(connect_soon())
    await manager.ensure_ready("/tmp/repo", port=4321)
    await task

    assert (tmp_data_dir / "User" / "settings.json").exists()


async def test_close_terminates_process(fake_spawn):
    manager = InstanceManager()

    async def connect_soon():
        await asyncio.sleep(0)
        manager.mark_connected()

    task = asyncio.create_task(connect_soon())
    await manager.ensure_ready("/tmp/repo", port=4321)
    await task

    assert manager._proc is not None
    assert manager.alive

    manager.close()
    assert not manager.alive
    assert manager._proc.returncode is None  # still running after terminate


def test_close_idempotent_when_no_proc():
    manager = InstanceManager()
    manager._alive = True
    manager.close()
    assert not manager.alive


def test_mark_disconnected_clears_alive():
    manager = InstanceManager()
    manager.mark_connected()
    assert manager.alive
    manager.mark_disconnected()
    assert not manager.alive
