"""Filesystem queue for the Cline bridge (ADR-0069, ADR-0073)."""

from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

RETENTION_SECONDS = 7 * 24 * 3600
STALE_HEARTBEAT_SECONDS = 300
CONTINUATION_IDLE_SECONDS = 300
LIFECYCLE_DIRS = ("pending", "claimed", "answered", "failed")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _epoch(stamp: str | None) -> float | None:
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def async_timeout_seconds() -> float:
    return float(os.getenv("CLINE_BRIDGE_ASYNC_TIMEOUT", "1800"))


def default_root() -> Path:
    return Path(os.path.expanduser(os.getenv("CLINE_BRIDGE_DIR", "~/.cline-bridge")))


class BridgeQueue:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()
        self.threads = self.root / "queue" / "threads"
        self.pending = self.locate(None) / "pending"
        self.claimed = self.locate(None) / "claimed"
        self.answered = self.locate(None) / "answered"
        self.failed = self.locate(None) / "failed"
        self.tmp = self.root / "tmp"
        self.lock_path = self.root / "queue.lock"
        self.heartbeat = self.root / "worker.alive"
        self.watchdog_heartbeat = self.root / "watchdog.alive"

    def locate(self, thread_id: str | None) -> Path:
        """Base directory holding a record's lifecycle dirs (ADR-0073)."""
        return self.root / "queue" if thread_id is None else self.threads / thread_id

    def ensure(self) -> None:
        for directory in (self.pending, self.claimed, self.answered, self.failed, self.tmp):
            directory.mkdir(parents=True, exist_ok=True)

    def _ensure_thread(self, thread_id: str) -> Path:
        base = self.locate(thread_id)
        for name in LIFECYCLE_DIRS:
            (base / name).mkdir(parents=True, exist_ok=True)
        return base

    def _thread_accepts_submissions(self, thread_id: str) -> bool:
        base = self.locate(thread_id)
        return base.is_dir() and not (base / ".swept").exists()

    @contextmanager
    def _lock(self):
        self.ensure()
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _write(self, path: Path, record: dict) -> None:
        staging = self.tmp / f"{record['id']}.{os.getpid()}.tmp"
        staging.write_text(json.dumps(record, indent=2))
        os.rename(staging, path)

    def submit(self, question: str, thread_id: str | None = None) -> dict:
        self.ensure()
        request_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        record = {
            "id": request_id,
            "thread_id": thread_id,
            "question": question,
            "submitted_at": _now(),
            "claimed_at": None,
            "claimed_by": None,
            "answered_at": None,
            "continuation_deadline": None,
            "answer": None,
            "reason": None,
        }
        live = thread_id is not None and self._thread_accepts_submissions(thread_id)
        base = self.locate(thread_id) if live else self.locate(None)
        self._write(base / "pending" / f"{request_id}.json", record)
        return record

    def claim_next(self, thread_id: str | None = None, worker_id: str | None = None) -> dict | None:
        with self._lock():
            source_dir = self.locate(thread_id) / "pending"
            names = sorted(path.name for path in source_dir.glob("*.json"))
            if not names:
                return None
            source = source_dir / names[0]
            record = json.loads(source.read_text())
            base = self._ensure_thread(record["thread_id"]) if record.get("thread_id") else self.locate(None)
            target = base / "claimed" / names[0]
            os.rename(source, target)
            record["claimed_at"] = _now()
            record["claimed_by"] = worker_id
            self._write(target, record)
            return record

    def answer(self, request_id: str, text: str, thread_id: str | None = None) -> bool:
        with self._lock():
            base = self.locate(thread_id)
            source = base / "claimed" / f"{request_id}.json"
            if not source.exists():
                return False
            record = json.loads(source.read_text())
            record["answered_at"] = _now()
            record["answer"] = text
            if record.get("thread_id"):
                deadline = datetime.now(timezone.utc) + timedelta(seconds=CONTINUATION_IDLE_SECONDS)
                record["continuation_deadline"] = (
                    deadline.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                )
            self._write(source, record)
            os.rename(source, base / "answered" / f"{request_id}.json")
            return True

    def fail(self, request_id: str, thread_id: str | None = None, reason: str | None = None) -> bool:
        with self._lock():
            base = self.locate(thread_id)
            name = f"{request_id}.json"
            for directory in ("claimed", "pending"):
                source = base / directory / name
                if source.exists():
                    self._mark_failed(source, base / "failed" / name, reason)
                    return True
            return False

    def _mark_failed(self, source: Path, target: Path, reason: str | None) -> None:
        try:
            record = json.loads(source.read_text())
        except (OSError, ValueError):
            record = None
        if record is not None:
            record["reason"] = reason
            self._write(source, record)
        os.rename(source, target)

    def read_answered(self, request_id: str, thread_id: str | None = None) -> dict | None:
        path = self.locate(thread_id) / "answered" / f"{request_id}.json"
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def touch_heartbeat(self) -> None:
        self.ensure()
        self.heartbeat.touch()
        os.utime(self.heartbeat, None)

    def worker_alive(self) -> bool:
        return self._fresh(self.heartbeat)

    def watchdog_alive(self) -> bool:
        return self._fresh(self.watchdog_heartbeat)

    @staticmethod
    def _fresh(path: Path) -> bool:
        try:
            return time.time() - path.stat().st_mtime <= STALE_HEARTBEAT_SECONDS
        except OSError:
            return False

    def counts(self) -> dict:
        self.ensure()
        return {
            name: len(list(directory.glob("*.json")))
            for name, directory in (
                ("pending", self.pending),
                ("claimed", self.claimed),
                ("answered", self.answered),
                ("failed", self.failed),
            )
        }

    def gc(self) -> int:
        self.ensure()
        now = time.time()
        self._sweep_abandoned_threads(now)
        expired = [self.answered, self.failed, self.tmp]
        for base in self._thread_dirs():
            expired += [base / "answered", base / "failed"]
        removed = 0
        for directory in expired:
            for path in directory.glob("*"):
                try:
                    if path.is_file() and now - path.stat().st_mtime > RETENTION_SECONDS:
                        path.unlink()
                        removed += 1
                except OSError:
                    pass
        return removed

    def _thread_dirs(self) -> list[Path]:
        return sorted(path for path in self.threads.glob("*") if path.is_dir())

    def _sweep_abandoned_threads(self, now: float) -> None:
        """Fail out threads whose holder died, then tombstone them (ADR-0073)."""
        with self._lock():
            for base in self._thread_dirs():
                if (base / ".swept").exists() or not self._thread_abandoned(base, now):
                    continue
                for directory in ("pending", "claimed"):
                    for path in (base / directory).glob("*.json"):
                        self._mark_failed(path, base / "failed" / path.name, "thread_abandoned")
                (base / ".swept").touch()

    def _thread_abandoned(self, base: Path, now: float) -> bool:
        claims = list((base / "claimed").glob("*.json"))
        if claims:
            # A held claim means the holder is mid-question; its own deadline is not yet due.
            stale = now - async_timeout_seconds()
            return any((_epoch(self._read(path).get("claimed_at")) or 0) < stale for path in claims)
        deadlines = [
            _epoch(self._read(path).get("continuation_deadline")) for path in (base / "answered").glob("*.json")
        ]
        deadlines = [deadline for deadline in deadlines if deadline is not None]
        return bool(deadlines) and max(deadlines) < now

    @staticmethod
    def _read(path: Path) -> dict:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
