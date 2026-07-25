import pytest

from vectors.locks import PathLockConflict, PathLockManager


def test_path_lock_conflicts_for_parent_child(tmp_path):
    manager = PathLockManager(tmp_path / "locks")
    with manager.lock("/tmp/project", "test"):
        with pytest.raises(PathLockConflict):
            with manager.lock("/tmp/project/src/file.py", "test"):
                pass


def test_path_lock_allows_unrelated_paths(tmp_path):
    manager = PathLockManager(tmp_path / "locks")
    with manager.lock("/tmp/project-a", "test"):
        with manager.lock("/tmp/project-b", "test"):
            assert len(manager.list_locks()) == 2


def test_cleanup_stale_lock(tmp_path):
    manager = PathLockManager(tmp_path / "locks")
    manager.lock_dir.mkdir(parents=True)
    stale = manager.lock_path_for("/tmp/stale")
    stale.write_text('{"pid": 99999999, "operation": "test", "path_key": "/tmp/stale", "timestamp": 1}')
    manager.cleanup_stale_locks()
    assert not stale.exists()
