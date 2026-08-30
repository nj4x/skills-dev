"""In-memory single-in-flight request queue (ADR: design/72 MCP tool interface).

No filesystem, no history: a handle dies with the MCP server. FIFO order,
one record dispatched at a time — matches the dedicated VS Code window's
one-task-at-a-time capacity (design/70).
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from bridge.logsetup import get_logger

logger = get_logger("queue")

REASONS = frozenset({"timeout", "instance_down", "cancelled", "unknown_handle", "internal_error"})

QUEUED = "queued"
DISPATCHED = "dispatched"
ANSWERED = "answered"
FAILED = "failed"


@dataclass
class Record:
    id: str
    question: str
    workspace: str
    status: str = QUEUED
    answer: str | None = None
    command: str | None = None
    reason: str | None = None
    tool_uses: int = 0
    last_event_at: float | None = None
    submitted_at: float = field(default_factory=time.monotonic)
    cline_task_id: str | None = None


class BridgeQueue:
    def __init__(self) -> None:
        self._pending: deque[Record] = deque()
        self._records: dict[str, Record] = {}
        self._in_flight: Record | None = None

    def submit(self, question: str, workspace: str) -> Record:
        record = Record(id=uuid.uuid4().hex, question=question, workspace=workspace)
        self._records[record.id] = record
        self._pending.append(record)
        logger.info("task submitted: id=%s workspace=%s", record.id, workspace)
        return record

    def next_dispatchable(self) -> Record | None:
        """Pop and mark the next pending record dispatched, unless one is already in flight."""
        if self._in_flight is not None or not self._pending:
            return None
        record = self._pending.popleft()
        record.status = DISPATCHED
        self._in_flight = record
        logger.info("task %s: queued -> dispatched", record.id)
        return record

    def in_flight(self) -> Record | None:
        return self._in_flight

    def busy(self) -> bool:
        return self._in_flight is not None or bool(self._pending)

    def all_records(self) -> list:
        return list(self._records.values())

    def record_tool_use(self) -> None:
        if self._in_flight is not None:
            self._in_flight.tool_uses += 1
            self._in_flight.last_event_at = time.monotonic()

    def bind_cline_task(self, cline_task_id: str | None) -> None:
        """Bind the in-flight record to cline-sr's own task id (ADR-0070)."""
        record = self._in_flight
        if record is None:
            logger.warning("TaskStart with no task in flight; nothing to bind (payload taskId=%s)", cline_task_id or "-")
            return
        if not cline_task_id:
            logger.warning("task %s: TaskStart carried no taskId; record stays unbound", record.id)
            return
        if record.cline_task_id is not None:
            if record.cline_task_id != cline_task_id:
                logger.warning(
                    "task %s: TaskStart taskId mismatch: bound=%s payload=%s; keeping original bind",
                    record.id, record.cline_task_id, cline_task_id,
                )
            return
        record.cline_task_id = cline_task_id
        record.last_event_at = time.monotonic()
        logger.info("task %s: bound to cline task %s", record.id, cline_task_id)

    def complete(self, answer: str, command: str | None, cline_task_id: str | None = None) -> None:
        record = self._in_flight
        if record is None:
            if self._recover_completion(cline_task_id, answer, command):
                return
            logger.warning("TaskComplete with no task in flight; answer dropped (payload taskId=%s)", cline_task_id or "-")
            return
        # Attempt recovery if the in-flight record is unbound and payload carries a taskId
        # that matches a failed record. This handles late completion for earlier tasks.
        if not record.cline_task_id and cline_task_id:
            if self._recover_completion(cline_task_id, answer, command):
                return
        # A mismatch requires both sides present: a completion without an id
        # (or against an unbound record) still applies, so a lost TaskStart
        # degrades to today's positional behavior instead of losing the answer.
        if record.cline_task_id and cline_task_id and record.cline_task_id != cline_task_id:
            if self._recover_completion(cline_task_id, answer, command):
                return
            logger.warning(
                "task %s: TaskComplete taskId mismatch: bound=%s payload=%s; answer dropped",
                record.id, record.cline_task_id, cline_task_id,
            )
            return
        record.status = ANSWERED
        record.answer = answer
        record.command = command
        record.last_event_at = time.monotonic()
        self._in_flight = None
        logger.info("task %s: dispatched -> answered", record.id)

    def _recover_completion(self, cline_task_id: str | None, answer: str, command: str | None) -> bool:
        """Resurrect a failed record whose bound cline taskId matches (ADR-0070 point 4)."""
        if not cline_task_id:
            return False
        for record in self._records.values():
            if record.status == FAILED and record.cline_task_id == cline_task_id:
                prior_reason = record.reason
                record.status = ANSWERED
                record.answer = answer
                record.command = command
                record.reason = None
                record.last_event_at = time.monotonic()
                logger.info(
                    "task %s: failed (reason=%s) -> answered (late completion, cline task %s)",
                    record.id, prior_reason, cline_task_id,
                )
                return True
        return False

    def cancel(self, reason: str = "cancelled", cline_task_id: str | None = None) -> None:
        record = self._in_flight
        if record is None:
            logger.warning("TaskCancel with no task in flight; ignored (payload taskId=%s)", cline_task_id or "-")
            return
        if record.cline_task_id is None:
            # Pre-bind cancel is the previous cline task's teardown, not a
            # cancellation of the record just dispatched (ADR-0070 point 3).
            logger.warning(
                "task %s: TaskCancel before TaskStart bind treated as previous-task teardown; ignored (payload taskId=%s)",
                record.id, cline_task_id or "-",
            )
            return
        if record.cline_task_id is not None and cline_task_id is not None and record.cline_task_id != cline_task_id:
            logger.warning(
                "task %s: TaskCancel taskId mismatch: bound=%s payload=%s; ignored",
                record.id, record.cline_task_id, cline_task_id,
            )
            return
        record.status = FAILED
        record.reason = reason
        self._in_flight = None
        logger.info("task %s: dispatched -> failed (reason=%s)", record.id, reason)

    def fail(self, record_id: str, reason: str) -> None:
        record = self._records.get(record_id)
        if record is None or record.status in (ANSWERED, FAILED):
            return
        prior = record.status
        record.status = FAILED
        record.reason = reason
        logger.info("task %s: %s -> failed (reason=%s)", record.id, prior, reason)
        if self._in_flight is record:
            self._in_flight = None
        else:
            try:
                self._pending.remove(record)
            except ValueError:
                pass

    def fail_in_flight(self, reason: str) -> None:
        if self._in_flight is not None:
            self.fail(self._in_flight.id, reason)

    def get(self, record_id: str) -> Record | None:
        return self._records.get(record_id)

    def sweep_expired(self, async_timeout: float) -> None:
        now = time.monotonic()
        for record in list(self._records.values()):
            if record.status in (QUEUED, DISPATCHED) and now - record.submitted_at > async_timeout:
                self.fail(record.id, "timeout")
