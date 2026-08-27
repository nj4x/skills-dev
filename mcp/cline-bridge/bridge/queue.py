"""Filesystem queue for the Cline bridge (ADR-0069)."""

from __future__ import annotations

import fcntl
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

RETENTION_SECONDS = 7 * 24 * 3600
STALE_HEARTBEAT_SECONDS = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def default_root() -> Path:
    return Path(os.path.expanduser(os.getenv("MCP_BRIDGE_DIR", "~/.mcp-bridge")))


class BridgeQueue:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()
        self.pending = self.root / "queue" / "pending"
        self.claimed = self.root / "queue" / "claimed"
        self.answered = self.root / "queue" / "answered"
        self.failed = self.root / "queue" / "failed"
        self.tmp = self.root / "tmp"
        self.lock_path = self.root / "queue.lock"
        self.heartbeat = self.root / "worker.alive"

    def ensure(self) -> None:
        for directory in (self.pending, self.claimed, self.answered, self.failed, self.tmp):
            directory.mkdir(parents=True, exist_ok=True)

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

    def submit(self, question: str) -> dict:
        self.ensure()
        request_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"
        record = {
            "id": request_id,
            "question": question,
            "submitted_at": _now(),
            "claimed_at": None,
            "answered_at": None,
            "answer": None,
        }
        self._write(self.pending / f"{request_id}.json", record)
        return record

    def claim_next(self) -> dict | None:
        with self._lock():
            names = sorted(path.name for path in self.pending.glob("*.json"))
            if not names:
                return None
            target = self.claimed / names[0]
            os.rename(self.pending / names[0], target)
            record = json.loads(target.read_text())
            record["claimed_at"] = _now()
            self._write(target, record)
            return record

    def answer(self, request_id: str, text: str) -> bool:
        with self._lock():
            source = self.claimed / f"{request_id}.json"
            if not source.exists():
                return False
            record = json.loads(source.read_text())
            record["answered_at"] = _now()
            record["answer"] = text
            self._write(source, record)
            os.rename(source, self.answered / f"{request_id}.json")
            return True

    def fail(self, request_id: str) -> bool:
        with self._lock():
            name = f"{request_id}.json"
            for directory in (self.claimed, self.pending):
                source = directory / name
                if source.exists():
                    os.rename(source, self.failed / name)
                    return True
            return False

    def read_answered(self, request_id: str) -> dict | None:
        path = self.answered / f"{request_id}.json"
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return None

    def touch_heartbeat(self) -> None:
        self.ensure()
        self.heartbeat.touch()
        os.utime(self.heartbeat, None)

    def worker_alive(self) -> bool:
        try:
            return time.time() - self.heartbeat.stat().st_mtime <= STALE_HEARTBEAT_SECONDS
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
        removed = 0
        for path in (*self.answered.glob("*.json"), *self.failed.glob("*.json"), *self.tmp.glob("*.tmp")):
            try:
                if now - path.stat().st_mtime > RETENTION_SECONDS:
                    path.unlink()
                    removed += 1
            except OSError:
                pass
        return removed
