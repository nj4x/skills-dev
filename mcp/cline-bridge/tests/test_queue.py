import json
import os
import time

import pytest

from bridge.queue import RETENTION_SECONDS, STALE_HEARTBEAT_SECONDS, BridgeQueue


@pytest.fixture
def queue(tmp_path):
    return BridgeQueue(tmp_path)


def test_submit_lands_in_pending_with_null_lifecycle_fields(queue):
    record = queue.submit("why?")
    stored = json.loads((queue.pending / f"{record['id']}.json").read_text())
    assert stored["question"] == "why?"
    assert stored["claimed_at"] is None
    assert stored["answered_at"] is None
    assert stored["answer"] is None


def test_claim_returns_oldest_first(queue):
    first = queue.submit("first")
    time.sleep(0.002)
    second = queue.submit("second")
    assert queue.claim_next()["id"] == first["id"]
    assert queue.claim_next()["id"] == second["id"]
    assert queue.claim_next() is None


def test_claim_moves_record_and_stamps_claimed_at(queue):
    record = queue.submit("why?")
    claimed = queue.claim_next()
    assert claimed["claimed_at"] is not None
    assert not (queue.pending / f"{record['id']}.json").exists()
    assert (queue.claimed / f"{record['id']}.json").exists()


def test_answer_moves_to_answered_and_is_readable(queue):
    record = queue.submit("why?")
    queue.claim_next()
    assert queue.answer(record["id"], "because") is True
    assert not (queue.claimed / f"{record['id']}.json").exists()
    assert queue.read_answered(record["id"])["answer"] == "because"


def test_answer_rejects_unclaimed_request(queue):
    record = queue.submit("why?")
    assert queue.answer(record["id"], "because") is False


def test_fail_marks_claimed_request_terminal_and_discards_late_answer(queue):
    record = queue.submit("why?")
    queue.claim_next()
    assert queue.fail(record["id"]) is True
    assert (queue.failed / f"{record['id']}.json").exists()
    assert queue.answer(record["id"], "too late") is False
    assert queue.read_answered(record["id"]) is None


def test_fail_marks_pending_request_terminal(queue):
    record = queue.submit("why?")
    assert queue.fail(record["id"]) is True
    assert (queue.failed / f"{record['id']}.json").exists()


def test_worker_alive_tracks_heartbeat_age(queue):
    assert queue.worker_alive() is False
    queue.touch_heartbeat()
    assert queue.worker_alive() is True
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    os.utime(queue.heartbeat, (stale, stale))
    assert queue.worker_alive() is False


def test_gc_removes_only_expired_terminal_records(queue):
    fresh = queue.submit("fresh")
    queue.claim_next()
    queue.answer(fresh["id"], "answer")
    old = queue.submit("old")
    queue.fail(old["id"])
    expired = time.time() - RETENTION_SECONDS - 1
    os.utime(queue.failed / f"{old['id']}.json", (expired, expired))

    assert queue.gc() == 1
    assert queue.read_answered(fresh["id"]) is not None
    assert not (queue.failed / f"{old['id']}.json").exists()


def test_root_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_BRIDGE_DIR", str(tmp_path / "elsewhere"))
    assert BridgeQueue().root == tmp_path / "elsewhere"
