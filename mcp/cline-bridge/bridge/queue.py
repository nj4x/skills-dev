"""Filesystem queue for the Cline bridge (ADR-0069, ADR-0073, ADR-0074)."""

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
MAX_POOL_SIZE = 10
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
        self.pool_conf = self.root / "pool.conf"
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

    def submit(self, question: str, repo_path: str, thread_id: str | None = None) -> dict:
        self.ensure()
        if thread_id is not None:
            first = self.read_first_in_thread(thread_id)
            if first is not None and first.get("repo_path") != repo_path:
                raise ValueError(
                    f"repo_path mismatch: thread uses {first.get('repo_path')}, got {repo_path}"
                )
        request_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        record = {
            "id": request_id,
            "thread_id": thread_id,
            "question": question,
            "repo_path": repo_path,
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

    def read_record(self, request_id: str, thread_id: str | None = None) -> tuple[str, dict] | None:
        """Lifecycle directory holding a record, and the record (ADR-0076).

        A thread's first message sits in top-level `pending/` until a worker claims it
        (ADR-0073), so a threaded lookup falls back there rather than reporting nothing.
        """
        bases = [self.locate(thread_id)]
        if thread_id is not None:
            bases.append(self.locate(None))
        for base in bases:
            for state in LIFECYCLE_DIRS:
                path = base / state / f"{request_id}.json"
                if path.exists():
                    record = self._read(path)
                    return (state, record) if record.get("thread_id") == thread_id else None
        return None

    def read_first_in_thread(self, thread_id: str) -> dict | None:
        """Oldest record of a thread — the one whose `repo_path` binds the rest (ADR-0075).

        Top-level `pending/` is scanned too: a thread's first message lands there and only
        moves under `threads/<id>/` when a worker claims it (ADR-0073).
        """
        base = self.locate(thread_id)
        paths = [path for name in LIFECYCLE_DIRS for path in (base / name).glob("*.json")]
        paths += list(self.pending.glob("*.json"))
        records = [record for record in map(self._read, paths) if record.get("thread_id") == thread_id]
        return min(records, key=lambda record: record["id"], default=None)

    def close_thread_if_idle(self, thread_id: str) -> bool:
        """Tombstone a thread whose continuation window has lapsed (ADR-0077).

        The worker leaving a thread writes the tombstone, not just `gc()`: while it is absent
        a follow-up still routes into `threads/<id>/pending/`, which only a worker holding the
        thread ever polls, so an untombstoned departure strands it there until the sweep fails
        it. Refusing to close while `pending/` holds anything is what lets a follow-up racing
        the close win — the worker polls once more and claims it.
        """
        base = self.locate(thread_id)
        with self._lock():
            if not base.is_dir():
                return True
            if any((base / "pending").glob("*.json")):
                return False
            latest = self._latest_continuation(base)
            if latest is not None and latest >= time.time():
                return False
            (base / ".swept").touch()
            return True

    def heartbeat_path(self, slot: int) -> Path:
        return self.root / f"worker-{slot}.alive"

    def pool_size(self) -> int:
        """Slot ceiling the watchdog wrote at startup.

        Absent when a worker starts before the watchdog (ADR-0074 risk 3): the ceiling is
        then unenforceable, so it falls back to the largest pool the ADR allows.
        """
        try:
            value = int(self.pool_conf.read_text().strip())
        except (OSError, ValueError):
            value = MAX_POOL_SIZE
        return max(1, min(value, MAX_POOL_SIZE))

    def claim_worker_slot(self) -> int | None:
        """Take the lowest free slot and start its heartbeat, or None if the pool is full."""
        with self._lock():
            for slot in range(1, self.pool_size() + 1):
                path = self.heartbeat_path(slot)
                if not self._fresh(path):
                    self._touch(path)
                    return slot
            return None

    def touch_heartbeat(self, slot: int) -> None:
        self.ensure()
        self._touch(self.heartbeat_path(slot))

    def worker_slots(self) -> list[tuple[int, bool]]:
        """Every slot with a heartbeat file, ascending, paired with its liveness."""
        slots = []
        for path in self.root.glob("worker-*.alive"):
            try:
                slot = int(path.name[len("worker-") : -len(".alive")])
            except ValueError:
                continue
            slots.append((slot, self._fresh(path)))
        return sorted(slots)

    def pool_offline(self) -> bool:
        """Whether the pool is known dead — the only case worth refusing a question over.

        A heartbeat is touched only by a `bridge` call, so a worker deep in a long answer
        looks exactly like a dead one. That reading is worth acting on only while the
        watchdog runs to act on it; with no watchdog the pool is assumed live and the
        request goes through to its own timeout rather than being refused on a guess.
        """
        return self.watchdog_alive() and not any(alive for _, alive in self.worker_slots())

    @staticmethod
    def _touch(path: Path) -> None:
        path.touch()
        os.utime(path, None)

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
        self._sweep_async_timeouts(now)
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

    def _sweep_async_timeouts(self, now: float) -> None:
        """Retire requests nobody answered inside the async budget (ADR-0076).

        Thread `claimed/` is left out: a held thread is `_sweep_abandoned_threads`'s to judge.
        """
        with self._lock():
            stale = now - async_timeout_seconds()
            sources = [self.pending, self.claimed]
            sources += [base / "pending" for base in self._thread_dirs()]
            for source in sources:
                for path in source.glob("*.json"):
                    submitted = _epoch(self._read(path).get("submitted_at"))
                    if submitted is not None and submitted < stale:
                        self._mark_failed(path, source.parent / "failed" / path.name, "timeout")

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
        latest = self._latest_continuation(base)
        return latest is not None and latest < now

    def _latest_continuation(self, base: Path) -> float | None:
        deadlines = [
            _epoch(self._read(path).get("continuation_deadline")) for path in (base / "answered").glob("*.json")
        ]
        return max((deadline for deadline in deadlines if deadline is not None), default=None)

    @staticmethod
    def _read(path: Path) -> dict:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}
