import asyncio
import os
import time
from pathlib import Path

import pytest

from bridge.queue import RETENTION_SECONDS, STALE_HEARTBEAT_SECONDS, BridgeQueue
from server import ask_peer_model

REPO = str(Path(__file__).parent)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_BRIDGE_DIR", str(tmp_path))
    monkeypatch.setenv("CLINE_BRIDGE_TIMEOUT", "2")
    return BridgeQueue(tmp_path)


async def _worker(queue, reply="because"):
    """Stand-in for the Cline-side loop: claim the next request, answer it."""
    while True:
        record = queue.claim_next()
        if record is not None:
            queue.answer(record["id"], f"{reply}: {record['question']}")
            return
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_round_trip_returns_the_workers_answer(queue):
    queue.touch_heartbeat(1)
    worker = asyncio.create_task(_worker(queue))
    result = await ask_peer_model("why?", REPO)
    await worker

    assert result["status"] == "answered"
    assert result["answer"] == "because: why?"
    assert result["reason"] is None
    assert queue.read_answered(result["id"])["answer"] == "because: why?"


@pytest.mark.asyncio
async def test_dead_worker_fails_fast_without_enqueuing(queue):
    started = time.monotonic()
    result = await ask_peer_model("why?", REPO)

    assert time.monotonic() - started < 1
    assert result == {
        "id": None,
        "status": "failed",
        "answer": None,
        "reason": "worker_offline",
        "watchdog": "offline",
    }
    assert queue.counts()["pending"] == 0


@pytest.mark.asyncio
async def test_dead_worker_with_live_watchdog_reports_a_restart_is_coming(queue):
    queue.watchdog_heartbeat.touch()
    result = await ask_peer_model("why?", REPO)

    assert result["reason"] == "worker_offline"
    assert result["watchdog"] == "alive"


@pytest.mark.asyncio
async def test_a_pool_of_stale_heartbeats_counts_as_offline(queue):
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    for slot in (1, 2):
        queue.touch_heartbeat(slot)
        os.utime(queue.heartbeat_path(slot), (stale, stale))
    assert (await ask_peer_model("why?", REPO))["reason"] == "worker_offline"


@pytest.mark.asyncio
async def test_one_live_slot_keeps_the_pool_up(queue):
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    queue.touch_heartbeat(1)
    os.utime(queue.heartbeat_path(1), (stale, stale))
    queue.touch_heartbeat(2)

    worker = asyncio.create_task(_worker(queue))
    result = await ask_peer_model("why?", REPO)
    await worker
    assert result["status"] == "answered"


@pytest.mark.asyncio
async def test_silent_worker_times_out_and_marks_the_record_failed(queue):
    queue.touch_heartbeat(1)
    result = await ask_peer_model("why?", REPO)

    assert result["status"] == "failed"
    assert result["reason"] == "timeout"
    assert (queue.failed / f"{result['id']}.json").exists()


@pytest.mark.asyncio
async def test_empty_question_is_a_caller_bug(queue):
    queue.touch_heartbeat(1)
    with pytest.raises(ValueError):
        await ask_peer_model("   ", REPO)


@pytest.mark.asyncio
async def test_repo_path_is_required_and_must_exist(queue, tmp_path):
    queue.touch_heartbeat(1)
    with pytest.raises(TypeError):
        await ask_peer_model("why?")
    with pytest.raises(ValueError, match="not an existing directory"):
        await ask_peer_model("why?", str(tmp_path / "gone"))
    assert queue.counts()["pending"] == 0


@pytest.mark.asyncio
async def test_the_record_carries_the_repo_path_to_the_worker(queue):
    queue.touch_heartbeat(1)
    worker = asyncio.create_task(_worker(queue))
    result = await ask_peer_model("why?", REPO)
    await worker
    assert queue.read_answered(result["id"])["repo_path"] == REPO


@pytest.mark.asyncio
async def test_call_sweeps_expired_terminal_records(queue):
    old = queue.submit("old", REPO)
    queue.fail(old["id"])
    expired = time.time() - RETENTION_SECONDS - 1
    os.utime(queue.failed / f"{old['id']}.json", (expired, expired))

    await ask_peer_model("why?", REPO)
    assert not (queue.failed / f"{old['id']}.json").exists()
