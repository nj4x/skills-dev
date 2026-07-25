"""Tests for RAGPipeline.sync_directory startup reconciliation."""

import asyncio
from types import SimpleNamespace

from vectors.config import Config
from vectors.paths import PathPolicy
from vectors.rag import RAGPipeline


class FakeVectorStore:
    """Minimal stand-in returning a fixed indexed-file listing."""

    def __init__(self, files, partial=False, scan_truncated=False):
        self._files = files
        self._partial = partial
        self._scan_truncated = scan_truncated

    async def list_indexed_files(self, skip=0, limit=100, base_dirs=None, max_scan_points=None):
        return {
            "files": self._files,
            "total_unique_files_scanned": len(self._files),
            "skip": skip,
            "limit": limit,
            "partial": self._partial,
            "scan_truncated": self._scan_truncated,
        }


def _make_pipeline(vector_store):
    pipeline = RAGPipeline(Config(), lm_client=object(), vector_store=vector_store)
    pipeline._initialized = True

    indexed_calls = []
    removed_calls = []

    async def fake_index_file(file_path, root_path=None):
        indexed_calls.append(str(file_path))
        return SimpleNamespace(success=True, skipped=False, error=None, chunks_indexed=1)

    async def fake_remove_document(file_path, dry_run=False):
        removed_calls.append(str(file_path))
        return {"success": True}

    pipeline.index_file = fake_index_file
    pipeline.remove_document = fake_remove_document
    return pipeline, indexed_calls, removed_calls


def _indexed_record(path):
    """Build an indexed listing record matching the on-disk path_key + mtime."""
    resolved = PathPolicy.resolve(path)
    return {
        "path_key": PathPolicy.path_key(resolved),
        "file_path": str(resolved),
        "mtime_ns": resolved.stat().st_mtime_ns,
    }


def test_sync_indexes_new_file(tmp_path):
    new_file = tmp_path / "new.py"
    new_file.write_text("print('new')")

    pipeline, indexed, removed = _make_pipeline(FakeVectorStore(files=[]))
    result = asyncio.run(pipeline.sync_directory(tmp_path))

    assert result["new"] == 1
    assert result["updated"] == 0
    assert result["removed"] == 0
    assert str(new_file.resolve()) in indexed
    assert removed == []


def test_sync_reindexes_changed_mtime(tmp_path):
    changed = tmp_path / "changed.py"
    changed.write_text("print('v1')")
    record = _indexed_record(changed)
    record["mtime_ns"] = record["mtime_ns"] - 1  # pretend disk is newer than index

    pipeline, indexed, removed = _make_pipeline(FakeVectorStore(files=[record]))
    result = asyncio.run(pipeline.sync_directory(tmp_path))

    assert result["new"] == 0
    assert result["updated"] == 1
    assert result["unchanged"] == 0
    assert str(changed.resolve()) in indexed


def test_sync_skips_unchanged_file(tmp_path):
    same = tmp_path / "same.py"
    same.write_text("print('same')")
    record = _indexed_record(same)  # mtime matches disk exactly

    pipeline, indexed, removed = _make_pipeline(FakeVectorStore(files=[record]))
    result = asyncio.run(pipeline.sync_directory(tmp_path))

    assert result["unchanged"] == 1
    assert result["new"] == 0
    assert result["updated"] == 0
    assert indexed == []  # unchanged files are never read/re-indexed


def test_sync_removes_deleted_file(tmp_path):
    present = tmp_path / "present.py"
    present.write_text("print('here')")
    ghost_record = {
        "path_key": PathPolicy.path_key(tmp_path / "gone.py"),
        "file_path": str((tmp_path / "gone.py").resolve()),
        "mtime_ns": 123,
    }

    pipeline, indexed, removed = _make_pipeline(
        FakeVectorStore(files=[_indexed_record(present), ghost_record])
    )
    result = asyncio.run(pipeline.sync_directory(tmp_path))

    assert result["removed"] == 1
    assert result["unchanged"] == 1
    assert str((tmp_path / "gone.py").resolve()) in removed


def test_sync_skips_deletions_when_scan_incomplete(tmp_path):
    present = tmp_path / "present.py"
    present.write_text("print('here')")
    ghost_record = {
        "path_key": PathPolicy.path_key(tmp_path / "gone.py"),
        "file_path": str((tmp_path / "gone.py").resolve()),
        "mtime_ns": 123,
    }

    pipeline, indexed, removed = _make_pipeline(
        FakeVectorStore(files=[_indexed_record(present), ghost_record], partial=True)
    )
    result = asyncio.run(pipeline.sync_directory(tmp_path))

    assert result["scan_incomplete"] is True
    assert result["deletions_skipped"] is True
    assert result["removed"] == 0
    assert removed == []  # incomplete view must not delete live files
