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

    def record_tool_use(self) -> None:
        if self._in_flight is not None:
            self._in_flight.tool_uses += 1
            self._in_flight.last_event_at = time.monotonic()

    def complete(self, answer: str, command: str | None) -> None:
        record = self._in_flight
        if record is None:
            return
        record.status = ANSWERED
        record.answer = answer
        record.command = command
        record.last_event_at = time.monotonic()
        self._in_flight = None
        logger.info("task %s: dispatched -> answered", record.id)

    def cancel(self, reason: str = "cancelled") -> None:
        record = self._in_flight
        if record is None:
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
