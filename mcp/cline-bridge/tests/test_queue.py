import json
import os
import pathlib
import time
from datetime import datetime, timedelta, timezone

import pytest

from bridge.queue import (
    CONTINUATION_IDLE_SECONDS,
    MAX_POOL_SIZE,
    RETENTION_SECONDS,
    STALE_HEARTBEAT_SECONDS,
    BridgeQueue,
)


REPO = str(pathlib.Path(__file__).parent)


@pytest.fixture
def queue(tmp_path):
    return BridgeQueue(tmp_path)


def _held_thread(queue, thread_id="t1", question="first"):
    """Submit and claim a thread's first message, so the thread directory exists."""
    record = queue.submit(question, REPO, thread_id=thread_id)
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
    record = queue.submit("why?", REPO)
    stored = json.loads((queue.pending / f"{record['id']}.json").read_text())
    assert stored["question"] == "why?"
    assert stored["claimed_at"] is None
    assert stored["answered_at"] is None
    assert stored["answer"] is None


def test_claim_returns_oldest_first(queue):
    first = queue.submit("first", REPO)
    time.sleep(0.002)
    second = queue.submit("second", REPO)
    assert queue.claim_next()["id"] == first["id"]
    assert queue.claim_next()["id"] == second["id"]
    assert queue.claim_next() is None


def test_claim_moves_record_and_stamps_claimed_at(queue):
    record = queue.submit("why?", REPO)
    claimed = queue.claim_next()
    assert claimed["claimed_at"] is not None
    assert not (queue.pending / f"{record['id']}.json").exists()
    assert (queue.claimed / f"{record['id']}.json").exists()


def test_answer_moves_to_answered_and_is_readable(queue):
    record = queue.submit("why?", REPO)
    queue.claim_next()
    assert queue.answer(record["id"], "because") is True
    assert not (queue.claimed / f"{record['id']}.json").exists()
    assert queue.read_answered(record["id"])["answer"] == "because"


def test_answer_rejects_unclaimed_request(queue):
    record = queue.submit("why?", REPO)
    assert queue.answer(record["id"], "because") is False


def test_fail_marks_claimed_request_terminal_and_discards_late_answer(queue):
    record = queue.submit("why?", REPO)
    queue.claim_next()
    assert queue.fail(record["id"]) is True
    assert (queue.failed / f"{record['id']}.json").exists()
    assert queue.answer(record["id"], "too late") is False
    assert queue.read_answered(record["id"]) is None


def test_fail_marks_pending_request_terminal(queue):
    record = queue.submit("why?", REPO)
    assert queue.fail(record["id"]) is True
    assert (queue.failed / f"{record['id']}.json").exists()


def test_pool_offline_tracks_heartbeat_age_per_slot_under_a_live_watchdog(queue):
    queue.ensure()
    queue.watchdog_heartbeat.touch()
    assert queue.pool_offline() is True
    queue.touch_heartbeat(2)
    assert queue.pool_offline() is False
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    os.utime(queue.heartbeat_path(2), (stale, stale))
    assert queue.pool_offline() is True


def test_pool_is_assumed_live_when_no_watchdog_is_running(queue):
    queue.ensure()
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    queue.touch_heartbeat(1)
    os.utime(queue.heartbeat_path(1), (stale, stale))

    assert queue.watchdog_alive() is False
    assert queue.pool_offline() is False


def test_worker_slots_report_every_heartbeat_file_in_ascending_order(queue):
    queue.ensure()
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    for slot in (10, 2, 1):
        queue.touch_heartbeat(slot)
    os.utime(queue.heartbeat_path(2), (stale, stale))

    assert queue.worker_slots() == [(1, True), (2, False), (10, True)]


def test_claim_worker_slot_takes_the_lowest_free_slot(queue):
    queue.pool_conf.parent.mkdir(parents=True, exist_ok=True)
    queue.pool_conf.write_text("3")

    assert queue.claim_worker_slot() == 1
    assert queue.claim_worker_slot() == 2
    assert queue.claim_worker_slot() == 3
    assert queue.claim_worker_slot() is None


def test_claim_worker_slot_reclaims_a_slot_whose_worker_went_stale(queue):
    queue.ensure()
    queue.pool_conf.write_text("2")
    queue.touch_heartbeat(1)
    queue.touch_heartbeat(2)
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    os.utime(queue.heartbeat_path(1), (stale, stale))

    assert queue.claim_worker_slot() == 1


def test_pool_size_falls_back_to_the_ceiling_when_the_watchdog_has_not_written_it(queue):
    queue.ensure()
    assert queue.pool_size() == MAX_POOL_SIZE
    queue.pool_conf.write_text("99")
    assert queue.pool_size() == MAX_POOL_SIZE
    queue.pool_conf.write_text("nonsense")
    assert queue.pool_size() == MAX_POOL_SIZE
    queue.pool_conf.write_text("2")
    assert queue.pool_size() == 2


def test_watchdog_alive_tracks_its_own_heartbeat_independently(queue):
    queue.ensure()
    queue.touch_heartbeat(1)
    assert queue.watchdog_alive() is False

    queue.watchdog_heartbeat.touch()
    assert queue.watchdog_alive() is True
    stale = time.time() - STALE_HEARTBEAT_SECONDS - 1
    os.utime(queue.watchdog_heartbeat, (stale, stale))
    assert queue.watchdog_alive() is False
    assert queue.worker_slots() == [(1, True)]


def test_gc_removes_only_expired_terminal_records(queue):
    fresh = queue.submit("fresh", REPO)
    queue.claim_next()
    queue.answer(fresh["id"], "answer")
    old = queue.submit("old", REPO)
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
    record = queue.submit("first", REPO, thread_id="t1")
    assert (queue.pending / f"{record['id']}.json").exists()

    claimed = queue.claim_next()
    assert claimed["thread_id"] == "t1"
    assert (queue.threads / "t1" / "claimed" / f"{record['id']}.json").exists()


def test_follow_up_routes_into_the_held_thread_and_hides_from_unfiltered_claim(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    follow_up = queue.submit("second", REPO, thread_id="t1")

    assert (queue.threads / "t1" / "pending" / f"{follow_up['id']}.json").exists()
    assert queue.claim_next() is None
    assert queue.claim_next(thread_id="t1")["id"] == follow_up["id"]


def test_thread_filtered_claim_ignores_top_level_work(queue):
    _held_thread(queue)
    queue.submit("unthreaded", REPO)
    assert queue.claim_next(thread_id="t1") is None


def test_claim_records_worker_id(queue):
    queue.submit("why?", REPO)
    assert queue.claim_next(worker_id="worker-2")["claimed_by"] == "worker-2"


def test_answer_and_fail_resolve_through_the_thread(queue):
    first = _held_thread(queue)
    assert queue.answer(first["id"], "because", thread_id="t1") is True
    assert queue.read_answered(first["id"], thread_id="t1")["answer"] == "because"
    assert queue.read_answered(first["id"]) is None

    follow_up = queue.submit("second", REPO, thread_id="t1")
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
    follow_up = queue.submit("second", REPO, thread_id="t1")
    answered = queue.threads / "t1" / "answered" / f"{first['id']}.json"
    _backdate(answered, continuation_deadline=_ago(CONTINUATION_IDLE_SECONDS))

    queue.gc()
    assert (queue.threads / "t1" / ".swept").exists()
    failed = json.loads((queue.threads / "t1" / "failed" / f"{follow_up['id']}.json").read_text())
    assert failed["reason"] == "thread_abandoned"


def test_sweep_leaves_a_live_thread_alone(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    follow_up = queue.submit("second", REPO, thread_id="t1")

    queue.gc()
    assert not (queue.threads / "t1" / ".swept").exists()
    assert (queue.threads / "t1" / "pending" / f"{follow_up['id']}.json").exists()


def test_submission_to_a_swept_thread_falls_back_to_top_level(queue):
    first = _held_thread(queue)
    _backdate(queue.threads / "t1" / "claimed" / f"{first['id']}.json", claimed_at=_ago(3600))
    queue.gc()

    late = queue.submit("second", REPO, thread_id="t1")
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


def test_submit_stores_the_repo_path_on_the_record(queue):
    record = queue.submit("why?", REPO)
    assert json.loads((queue.pending / f"{record['id']}.json").read_text())["repo_path"] == REPO


def test_thread_follow_up_must_reuse_the_first_messages_repo_path(queue):
    _held_thread(queue)
    with pytest.raises(ValueError, match="repo_path mismatch"):
        queue.submit("second", "/elsewhere", thread_id="t1")
    assert queue.submit("second", REPO, thread_id="t1")["repo_path"] == REPO


def test_thread_binding_holds_before_the_first_message_is_claimed(queue):
    queue.submit("first", REPO, thread_id="t1")
    with pytest.raises(ValueError, match="repo_path mismatch"):
        queue.submit("second", "/elsewhere", thread_id="t1")


def test_read_first_in_thread_returns_the_oldest_message_wherever_it_sits(queue):
    first = _held_thread(queue)
    queue.answer(first["id"], "one", thread_id="t1")
    queue.submit("second", REPO, thread_id="t1")

    assert queue.read_first_in_thread("t1")["id"] == first["id"]
    assert queue.read_first_in_thread("unknown") is None


def test_read_record_reports_the_lifecycle_dir_holding_a_record(queue):
    record = queue.submit("why?", REPO)
    assert queue.read_record(record["id"])[0] == "pending"
    queue.claim_next()
    assert queue.read_record(record["id"])[0] == "claimed"

    queue.answer(record["id"], "because")
    state, found = queue.read_record(record["id"])
    assert (state, found["answer"]) == ("answered", "because")
    assert queue.read_record("no-such-id") is None


def test_read_record_finds_a_threads_first_message_before_it_is_claimed(queue):
    first = queue.submit("first", REPO, thread_id="t1")
    assert queue.read_record(first["id"], thread_id="t1")[0] == "pending"
    queue.claim_next()
    assert queue.read_record(first["id"], thread_id="t1")[0] == "claimed"


def test_read_record_rejects_a_handle_belonging_to_another_thread(queue):
    record = queue.submit("why?", REPO)
    assert queue.read_record(record["id"], thread_id="t1") is None


def test_async_sweep_times_out_stale_top_level_records(queue):
    claimed = queue.submit("claimed but unanswered", REPO)
    queue.claim_next()
    unclaimed = queue.submit("nobody took it", REPO)
    recent = queue.submit("just submitted", REPO)
    _backdate(queue.claimed / f"{claimed['id']}.json", submitted_at=_ago(3600))
    _backdate(queue.pending / f"{unclaimed['id']}.json", submitted_at=_ago(3600))

    queue.gc()
    assert json.loads((queue.failed / f"{claimed['id']}.json").read_text())["reason"] == "timeout"
    assert (queue.failed / f"{unclaimed['id']}.json").exists()
    assert (queue.pending / f"{recent['id']}.json").exists()


def test_async_sweep_times_out_an_unclaimed_thread_follow_up(queue):
    _held_thread(queue)
    follow_up = queue.submit("second", REPO, thread_id="t1")
    _backdate(queue.threads / "t1" / "pending" / f"{follow_up['id']}.json", submitted_at=_ago(3600))

    queue.gc()
    failed = queue.threads / "t1" / "failed" / f"{follow_up['id']}.json"
    assert json.loads(failed.read_text())["reason"] == "timeout"


def test_a_held_thread_claim_outlives_the_blocking_timeout_and_the_async_sweep(queue):
    first = _held_thread(queue)
    claimed = queue.threads / "t1" / "claimed" / f"{first['id']}.json"
    _backdate(claimed, submitted_at=_ago(3600), claimed_at=_ago(600))

    queue.gc()
    assert claimed.exists()
    assert not (queue.threads / "t1" / ".swept").exists()


def test_root_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CLINE_BRIDGE_DIR", str(tmp_path / "elsewhere"))
    assert BridgeQueue().root == tmp_path / "elsewhere"
