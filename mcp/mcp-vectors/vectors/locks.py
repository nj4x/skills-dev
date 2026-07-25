"""Same-host path operation locks for mcp-vectors mutations."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .paths import PathPolicy


@dataclass
class LockInfo:
    path_key: str
    operation: str
    pid: int
    timestamp: float
    lock_path: str


class PathLockConflict(RuntimeError):
    """Raised when another process holds an overlapping path lock."""

    def __init__(self, requested_path: str, conflicts: list[LockInfo]):
        self.requested_path = requested_path
        self.conflicts = conflicts
        super().__init__(f"Path lock conflict for {requested_path}: {len(conflicts)} overlapping operation(s)")


class PathOperationLock:
    """Context manager for one held path operation lock."""

    def __init__(self, manager: "PathLockManager", path_key: str, operation: str):
        self.manager = manager
        self.path_key = path_key
        self.operation = operation
        self.lock_path = manager.lock_path_for(path_key)
        self._file = None

    def __enter__(self) -> "PathOperationLock":
        self.manager.acquire(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    def release(self) -> None:
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
            try:
                self.lock_path.unlink()
            except FileNotFoundError:
                pass


class PathLockManager:
    """Coordinates mutating operations on overlapping paths on this host."""

    def __init__(self, lock_dir: str | Path = "/tmp/mcp-vectors-locks"):
        self.lock_dir = Path(lock_dir)
        self.registry_path = self.lock_dir / "path-registry.lock"

    def lock(self, path: str | Path, operation: str) -> PathOperationLock:
        return PathOperationLock(self, PathPolicy.path_key(path), operation)

    def acquire(self, lock: PathOperationLock) -> None:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "a+") as registry:
            fcntl.flock(registry.fileno(), fcntl.LOCK_EX)
            try:
                self.cleanup_stale_locks()
                conflicts = self.find_conflicts(lock.path_key)
                if conflicts:
                    raise PathLockConflict(lock.path_key, conflicts)

                lock._file = open(lock.lock_path, "a+")
                fcntl.flock(lock._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                lock._file.seek(0)
                lock._file.truncate()
                payload = {
                    "pid": os.getpid(),
                    "operation": lock.operation,
                    "path_key": lock.path_key,
                    "timestamp": time.time(),
                }
                lock._file.write(json.dumps(payload))
                lock._file.flush()
            finally:
                fcntl.flock(registry.fileno(), fcntl.LOCK_UN)

    def find_conflicts(self, path_key: str) -> list[LockInfo]:
        conflicts = []
        for info in self.list_locks():
            if PathPolicy.overlaps(path_key, info.path_key):
                conflicts.append(info)
        return conflicts

    def list_locks(self) -> list[LockInfo]:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        locks = []
        for lock_path in self.lock_dir.glob("path-*.lock"):
            info = self._read_lock(lock_path)
            if info is not None:
                locks.append(info)
        return locks

    def cleanup_stale_locks(self) -> None:
        for info in self.list_locks():
            if not self._is_pid_alive(info.pid):
                try:
                    Path(info.lock_path).unlink()
                except FileNotFoundError:
                    pass

    def lock_path_for(self, path_key: str) -> Path:
        digest = hashlib.sha256(path_key.encode()).hexdigest()[:32]
        return self.lock_dir / f"path-{digest}.lock"

    def _read_lock(self, lock_path: Path) -> Optional[LockInfo]:
        try:
            text = lock_path.read_text().strip()
            if not text:
                return None
            data = json.loads(text)
            return LockInfo(
                path_key=data.get("path_key", ""),
                operation=data.get("operation", "unknown"),
                pid=int(data.get("pid", 0)),
                timestamp=float(data.get("timestamp", 0)),
                lock_path=str(lock_path),
            )
        except Exception:
            return None

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
