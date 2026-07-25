"""Tests for IndexEventHandler change classification.

These reproduce the macOS atomic-save bug: a save writes a temp file then
rename-replaces the target, emitting both a change and a delete for the target in
one debounce batch. The handler must classify by real disk state at process time so
the surviving target is (re)indexed rather than removed from the index.
"""

import asyncio

from vectors.watcher import FileWatcher, IndexEventHandler, WatcherConfig
from watchdog.events import (
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
)


def _make_handler(tmp_path):
    """Build a handler with recording callbacks. Returns (handler, changed, deleted, dirs)."""
    changed: list = []
    deleted: list = []
    dirs: list = []

    handler = IndexEventHandler(
        config=WatcherConfig(watch_dir=tmp_path, respect_gitignore=False),
        on_files_changed=lambda paths: changed.extend(paths),
        on_files_deleted=lambda paths: deleted.extend(paths),
        on_dirs_touched=lambda touched: dirs.extend(touched),
    )
    return handler, changed, deleted, dirs


def test_atomic_save_reindexes_target(tmp_path):
    """write-temp -> rename-replace must (re)index the target, not delete it."""
    target = tmp_path / "module.py"
    tmp = tmp_path / "module.py.tmp.123.abc"
    target.write_text("print('new contents')")  # final state on disk: target exists

    handler, changed, deleted, _ = _make_handler(tmp_path)

    # The event sequence an atomic save emits, with the target's delete arriving
    # last (the case that previously cannibalized the pending change).
    handler.on_created(FileCreatedEvent(str(tmp)))
    handler.on_modified(FileModifiedEvent(str(tmp)))
    handler.on_moved(FileMovedEvent(str(tmp), str(target)))
    handler.on_deleted(FileDeletedEvent(str(tmp)))

    asyncio.run(handler._process_changes())

    assert target in changed, "target should be (re)indexed after atomic save"
    assert target not in deleted, "target must not be removed from the index"


def test_new_file_is_indexed(tmp_path):
    """A brand-new file (direct create and via rename) routes to indexing."""
    direct = tmp_path / "direct.py"
    renamed = tmp_path / "renamed.py"
    direct.write_text("x = 1")
    renamed.write_text("y = 2")

    handler, changed, deleted, _ = _make_handler(tmp_path)
    handler.on_created(FileCreatedEvent(str(direct)))
    handler.on_moved(FileMovedEvent(str(tmp_path / "renamed.py.tmp"), str(renamed)))

    asyncio.run(handler._process_changes())

    assert direct in changed
    assert renamed in changed
    # The move source (a now-gone temp) routes to a harmless delete no-op; the
    # real files must never be on the delete path.
    assert direct not in deleted
    assert renamed not in deleted


def test_genuine_delete_is_removed(tmp_path):
    """A file removed from disk routes to deletion."""
    gone = tmp_path / "gone.py"  # never created -> does not exist

    handler, changed, deleted, _ = _make_handler(tmp_path)
    handler.on_deleted(FileDeletedEvent(str(gone)))

    asyncio.run(handler._process_changes())

    assert gone in deleted
    assert changed == []


def test_touched_dirs_collected_for_reconcile(tmp_path):
    """Parent directory of a touched file is surfaced for the reconcile safety net."""
    f = tmp_path / "sub" / "a.py"
    f.parent.mkdir()
    f.write_text("a = 1")

    handler, _, _, dirs = _make_handler(tmp_path)
    handler.on_created(FileCreatedEvent(str(f)))

    asyncio.run(handler._process_changes())

    assert f.parent in dirs


def test_file_watcher_rejects_excluded_worktree_root_without_scheduling(monkeypatch, tmp_path):
    """Excluded roots should be rejected before lock or observer setup."""
    worktree = tmp_path / ".claude" / "worktrees" / "agent-1"
    worktree.mkdir(parents=True)

    watcher = FileWatcher(
        watch_dir=worktree,
        index_callback=lambda _: None,
        delete_callback=lambda _: None,
        respect_gitignore=False,
    )

    def fail_acquire_lock():
        raise AssertionError("excluded watch roots should fail before lock acquisition")

    monkeypatch.setattr(watcher, "_acquire_lock", fail_acquire_lock)

    loop = asyncio.new_event_loop()
    try:
        assert watcher.start(loop) is False
        assert watcher.is_running is False
        assert watcher.has_lock is False
    finally:
        loop.close()

    assert watcher._observer is None
    assert watcher._handler is None


async def _wait_until(predicate):
    """Yield until predicate is true, with a short bounded retry budget."""
    for _ in range(20):
        if predicate():
            return
        await asyncio.sleep(0.01)
    assert predicate(), "Timed out waiting for watcher callback"


def test_parent_reconcile_preserves_indexed_subdirectory_file(tmp_path):
    """C2 — non-recursive parent reconciliation must not remove indexed descendants.

    A watcher reconciliation event for a parent directory calls sync_directory with
    recursive=False.  The indexed child file must remain because that shallow scan
    cannot prove a descendant is deleted.
    """
    from types import SimpleNamespace
    from vectors.rag import RAGPipeline

    child = tmp_path / "subdir" / "indexed.py"
    child.parent.mkdir()
    child.write_text("x = 1")
    child_key = str(child.resolve())

    # Stub the pipeline collaborators so we exercise sync_directory's diff logic
    # without Qdrant/LM Studio dependencies.
    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline._initialized = True
    pipeline.config = SimpleNamespace(max_files_per_scan=100, qdrant_url=None)
    pipeline.safety = SimpleNamespace(should_traverse_path=lambda _: SimpleNamespace(action="index"))
    pipeline.collect_indexable_files = lambda root, recursive, respect_gitignore: SimpleNamespace(
        files=[], partial=False  # recursive=False parent scan does not enumerate child
    )
    pipeline.vector_store = SimpleNamespace(
        list_indexed_files=lambda **_: asyncio.sleep(
            0,
            result={"files": [{"path_key": child_key, "file_path": child_key}], "partial": False, "scan_truncated": False},
        )
    )
    removed = []

    async def unexpected_index(_path, root_path):
        raise AssertionError("No child should be indexed during parent-only reconcile")

    async def record_remove(path):
        removed.append(path)

    pipeline.index_file = unexpected_index
    pipeline.remove_file = record_remove

    result = asyncio.run(pipeline.sync_directory(tmp_path, recursive=False, respect_gitignore=False))

    assert result["success"] is True
    assert removed == [], "Shallow reconcile removed indexed subdirectory file (C2 regression)"


def test_watcher_stop_cancels_and_drains_pending_tasks(tmp_path):
    """M1 — stop() must cancel and await all pending tasks before returning.

    Verifies:
    - Every tracked task is cancelled after stop().
    - The _pending_tasks set is cleared.
    - stop() does not leave any un-awaited tasks (i.e., all tasks are done).
    """
    async def exercise_stop():
        watcher = FileWatcher(
            watch_dir=tmp_path,
            index_callback=lambda _: None,
            delete_callback=lambda _: None,
            respect_gitignore=False,
        )

        started = asyncio.Event()

        async def slow_task():
            started.set()
            await asyncio.sleep(60)  # effectively never completes in test time

        task = asyncio.create_task(slow_task())
        watcher._pending_tasks.add(task)
        watcher._running = True

        # Give the task a chance to reach its first await before stop() cancels it
        await started.wait()

        await watcher.stop()

        # Task must be finished (cancelled) and the tracking set must be clear
        assert task.done(), "Task should be done after stop()"
        assert task.cancelled(), "Task should have been cancelled by stop()"
        assert watcher._pending_tasks == set(), "Pending task set must be empty after stop()"

    asyncio.run(exercise_stop())
