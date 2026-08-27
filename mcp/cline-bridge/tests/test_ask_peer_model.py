import asyncio
import os
import time

import pytest

from bridge.queue import RETENTION_SECONDS, STALE_HEARTBEAT_SECONDS, BridgeQueue
from server import ask_peer_model


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_BRIDGE_DIR", str(tmp_path))
    monkeypatch.setenv("MCP_BRIDGE_TIMEOUT", "2")
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
    queue.touch_heartbeat()
    worker = asyncio.create_task(_worker(queue))
    result = await ask_peer_model("why?")
    await worker

    assert result["status"] == "answered"
    assert result["answer"] == "because: why?"
    assert result["reason"] is None
    assert queue.read_answered(result["id"])["answer"] == "because: why?"


@pytest.mark.asyncio
async def test_dead_worker_fails_fast_without_enqueuing(queue):
    started = time.monotonic()
    result = await ask_peer_model("why?")

    assert time.monotonic() - started < 1
    assert result == {"id": None, "status": "failed", "answer": None, "reason": "worker_offline"}
    assert queue.counts()["pending"] == 0


@pytest.mark.asyncio
async def test_stale_heartbeat_counts_as_offline(queue):
    queue.touch_heartbeat()
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    os.utime(queue.heartbeat, (stale, stale))
    assert (await ask_peer_model("why?"))["reason"] == "worker_offline"


@pytest.mark.asyncio
async def test_silent_worker_times_out_and_marks_the_record_failed(queue):
    queue.touch_heartbeat()
    result = await ask_peer_model("why?")

    assert result["status"] == "failed"
    assert result["reason"] == "timeout"
    assert (queue.failed / f"{result['id']}.json").exists()


@pytest.mark.asyncio
async def test_empty_question_is_a_caller_bug(queue):
    queue.touch_heartbeat()
    with pytest.raises(ValueError):
        await ask_peer_model("   ")


@pytest.mark.asyncio
async def test_call_sweeps_expired_terminal_records(queue):
    old = queue.submit("old")
    queue.fail(old["id"])
    expired = time.time() - RETENTION_SECONDS - 1
    os.utime(queue.failed / f"{old['id']}.json", (expired, expired))

    await ask_peer_model("why?")
    assert not (queue.failed / f"{old['id']}.json").exists()
