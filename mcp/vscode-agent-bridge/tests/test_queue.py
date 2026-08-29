from bridge.queue import ANSWERED, DISPATCHED, FAILED, QUEUED, BridgeQueue


def test_submit_starts_queued():
    queue = BridgeQueue()
    record = queue.submit("question", "/tmp")
    assert record.status == QUEUED
    assert queue.get(record.id) is record


def test_next_dispatchable_marks_in_flight():
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    dispatched = queue.next_dispatchable()
    assert dispatched is record
    assert record.status == DISPATCHED
    assert queue.in_flight() is record


def test_single_in_flight_blocks_second_dispatch():
    queue = BridgeQueue()
    first = queue.submit("q1", "/tmp")
    second = queue.submit("q2", "/tmp")
    assert queue.next_dispatchable() is first
    assert queue.next_dispatchable() is None  # still busy
    assert second.status == QUEUED


def test_complete_frees_in_flight_for_next_dispatch():
    queue = BridgeQueue()
    first = queue.submit("q1", "/tmp")
    second = queue.submit("q2", "/tmp")
    queue.next_dispatchable()
    queue.complete("answer", "ls -la")
    assert first.status == ANSWERED
    assert first.answer == "answer"
    assert first.command == "ls -la"
    assert queue.in_flight() is None
    assert queue.next_dispatchable() is second


def test_cancel_marks_in_flight_failed():
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()
    queue.cancel("cancelled")
    assert record.status == FAILED
    assert record.reason == "cancelled"
    assert queue.in_flight() is None


def test_record_tool_use_only_touches_in_flight():
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    queue.record_tool_use()  # nothing in flight yet — no-op, no crash
    assert record.tool_uses == 0
    queue.next_dispatchable()
    queue.record_tool_use()
    queue.record_tool_use()
    assert record.tool_uses == 2
    assert record.last_event_at is not None


def test_fail_queued_record_removes_from_pending():
    queue = BridgeQueue()
    first = queue.submit("q1", "/tmp")
    second = queue.submit("q2", "/tmp")
    queue.next_dispatchable()  # first is in flight
    queue.fail(second.id, "timeout")
    assert second.status == FAILED
    assert second.reason == "timeout"
    queue.complete("a", None)
    assert queue.next_dispatchable() is None  # second was removed, nothing left


def test_fail_is_idempotent_after_terminal_state():
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()
    queue.complete("answer", None)
    queue.fail(record.id, "timeout")  # must not clobber an answered record
    assert record.status == ANSWERED
    assert record.answer == "answer"


def test_fail_in_flight_clears_slot():
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()
    queue.fail_in_flight("instance_down")
    assert record.status == FAILED
    assert record.reason == "instance_down"
    assert queue.in_flight() is None


def test_fail_in_flight_noop_when_idle():
    queue = BridgeQueue()
    queue.fail_in_flight("instance_down")  # must not raise


def test_sweep_expired_only_touches_queued_and_dispatched(monkeypatch):
    import time

    queue = BridgeQueue()
    stale = queue.submit("q1", "/tmp")
    fresh = queue.submit("q2", "/tmp")

    real_monotonic = time.monotonic
    monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() - 10_000)
    stale.submitted_at = time.monotonic()
    monkeypatch.setattr(time, "monotonic", real_monotonic)

    queue.sweep_expired(async_timeout=1.0)
    assert stale.status == FAILED
    assert stale.reason == "timeout"
    assert fresh.status == QUEUED


def test_get_unknown_handle_returns_none():
    queue = BridgeQueue()
    assert queue.get("nope") is None


def test_status_transitions_logged(caplog):
    caplog.set_level("INFO", logger="vscode-agent-bridge.queue")
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()
    queue.complete("done", None)
    messages = [r.getMessage() for r in caplog.records]
    assert any(f"task submitted: id={record.id}" in m for m in messages)
    assert any(f"task {record.id}: queued -> dispatched" in m for m in messages)
    assert any(f"task {record.id}: dispatched -> answered" in m for m in messages)


def test_failure_transition_logged_with_reason(caplog):
    caplog.set_level("INFO", logger="vscode-agent-bridge.queue")
    queue = BridgeQueue()
    record = queue.submit("q", "/tmp")
    queue.next_dispatchable()
    queue.cancel("cancelled")
    messages = [r.getMessage() for r in caplog.records]
    assert any(f"task {record.id}: dispatched -> failed (reason=cancelled)" in m for m in messages)
