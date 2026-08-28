import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from bridge.queue import (
    CONTINUATION_IDLE_SECONDS,
    RETENTION_SECONDS,
    STALE_HEARTBEAT_SECONDS,
    BridgeQueue,
)


@pytest.fixture
def queue(tmp_path):
    return BridgeQueue(tmp_path)


def _held_thread(queue, thread_id="t1", question="first"):
    """Submit and claim a thread's first message, so the thread directory exists."""
    record = queue.submit(question, thread_id=thread_id)
    queue.claim_next()
    return record


def _ago(seconds):
    moment = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _backdate(path, **fields):
    record = json.loads(path.read_text())
    record.update(fields)
    path.write_text(json.dumps(record))


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


def test_watchdog_alive_tracks_its_own_heartbeat_independently(queue):
    queue.ensure()
    queue.touch_heartbeat()
    assert queue.watchdog_alive() is False

    queue.watchdog_heartbeat.touch()
    assert queue.watchdog_alive() is True
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    os.utime(queue.watchdog_heartbeat, (stale, stale))
    assert queue.watchdog_alive() is False
    assert queue.worker_alive() is True


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


def test_locate_resolves_thread_base_and_falls_back_to_top_level(queue):
    assert queue.locate(None) == queue.pending.parent
    assert queue.locate("t1") == queue.threads / "t1"


def test_first_thread_message_lands_top_level_then_claim_moves_it_into_the_thread(queue):
    record = queue.submit("first", thread_id="t1")
    assert (queue.pending / f"{record['id']}.json").exists()

    claimed = queue.claim_next()
    assert claimed["thread_id"] == "t1"
    assert (queue.threads / "t1" / "claimed" / f"{record['id']}.json").exists()


def test_follow_up_routes_into_the_held_thread_and_hides_from_unfiltered_claim(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    follow_up = queue.submit("second", thread_id="t1")

    assert (queue.threads / "t1" / "pending" / f"{follow_up['id']}.json").exists()
    assert queue.claim_next() is None
    assert queue.claim_next(thread_id="t1")["id"] == follow_up["id"]


def test_thread_filtered_claim_ignores_top_level_work(queue):
    _held_thread(queue)
    queue.submit("unthreaded")
    assert queue.claim_next(thread_id="t1") is None


def test_claim_records_worker_id(queue):
    queue.submit("why?")
    assert queue.claim_next(worker_id="worker-2")["claimed_by"] == "worker-2"


def test_answer_and_fail_resolve_through_the_thread(queue):
    first = _held_thread(queue)
    assert queue.answer(first["id"], "because", thread_id="t1") is True
    assert queue.read_answered(first["id"], thread_id="t1")["answer"] == "because"
    assert queue.read_answered(first["id"]) is None

    follow_up = queue.submit("second", thread_id="t1")
    assert queue.fail(follow_up["id"], thread_id="t1", reason="timeout") is True
    failed = json.loads((queue.threads / "t1" / "failed" / f"{follow_up['id']}.json").read_text())
    assert failed["reason"] == "timeout"


def test_answering_a_thread_sets_the_continuation_deadline(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "because", thread_id="t1")
    answered = queue.read_answered(first["id"], thread_id="t1")
    assert answered["continuation_deadline"] > answered["answered_at"]


def test_sweep_tombstones_a_thread_whose_holder_died_mid_question(queue):
    first = _held_thread(queue)
    claimed = queue.threads / "t1" / "claimed" / f"{first['id']}.json"
    _backdate(claimed, claimed_at=_ago(3600))

    queue.gc()
    assert (queue.threads / "t1" / ".swept").exists()
    assert (queue.threads / "t1" / "failed" / f"{first['id']}.json").exists()


def test_sweep_tombstones_a_thread_past_its_continuation_deadline_and_fails_its_backlog(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    follow_up = queue.submit("second", thread_id="t1")
    answered = queue.threads / "t1" / "answered" / f"{first['id']}.json"
    _backdate(answered, continuation_deadline=_ago(CONTINUATION_IDLE_SECONDS))

    queue.gc()
    assert (queue.threads / "t1" / ".swept").exists()
    failed = json.loads((queue.threads / "t1" / "failed" / f"{follow_up['id']}.json").read_text())
    assert failed["reason"] == "thread_abandoned"


def test_sweep_leaves_a_live_thread_alone(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    follow_up = queue.submit("second", thread_id="t1")

    queue.gc()
    assert not (queue.threads / "t1" / ".swept").exists()
    assert (queue.threads / "t1" / "pending" / f"{follow_up['id']}.json").exists()


def test_submission_to_a_swept_thread_falls_back_to_top_level(queue):
    first = _held_thread(queue)
    _backdate(queue.threads / "t1" / "claimed" / f"{first['id']}.json", claimed_at=_ago(3600))
    queue.gc()

    late = queue.submit("second", thread_id="t1")
    assert (queue.pending / f"{late['id']}.json").exists()
    assert queue.claim_next()["id"] == late["id"]


def test_gc_expires_thread_history_under_the_same_retention(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    answered = queue.threads / "t1" / "answered" / f"{first['id']}.json"
    expired = time.time() - RETENTION_SECONDS - 1
    os.utime(answered, (expired, expired))

    assert queue.gc() == 1
    assert not answered.exists()


def test_root_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_BRIDGE_DIR", str(tmp_path / "elsewhere"))
    assert BridgeQueue().root == tmp_path / "elsewhere"
