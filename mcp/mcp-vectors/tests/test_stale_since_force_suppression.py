"""Tests for stale_since suppression when force=True (ticket 05)."""

import asyncio
import time

from vectors.testing import InMemoryVectorStore
from vectors.rag import RAGPipeline
from vectors.config import Config
from server import index_codebase


async def _create_stale_store_no_timestamps():
    """Create an InMemoryVectorStore with points that have NO indexed_at field (T04 scenario)."""
    store = InMemoryVectorStore(vector_size=384)
    await store.initialize()

    # Manually inject a record without indexed_at to simulate pre-upgrade metadata
    store._points.append({
        "id": "test-point-no-ts",
        "vector": [0.1] * 384,
        "payload": {
            "file_path": "/tmp/test_no_timestamp.py",
            "path_key": "/tmp/test_no_timestamp.py",
            "file_name": "no_ts.py",
            "chunk_id": 0,
            "chunk_text": "print('no timestamp')",
            "start_char": 0,
            "end_char": 20,
            "root_path": "/tmp",
            "root_id": "/tmp",
            "file_type": "python",
            "extension": ".py",
            "metadata_version": 1,
            # Note: no indexed_at field
        },
    })
    return store


async def _create_stale_store_old_timestamp():
    """Create an InMemoryVectorStore with points that have an OLD indexed_at (30 days ago)."""
    store = InMemoryVectorStore(vector_size=384)
    await store.initialize()

    # Inject a record with an old timestamp (30 days ago)
    old_timestamp = time.time() - (30 * 24 * 3600)  # 30 days ago
    store._points.append({
        "id": "test-point-old",
        "vector": [0.1] * 384,
        "payload": {
            "file_path": "/tmp/test_old_timestamp.py",
            "path_key": "/tmp/test_old_timestamp.py",
            "file_name": "old_ts.py",
            "chunk_id": 0,
            "chunk_text": "print('old timestamp')",
            "start_char": 0,
            "end_char": 21,
            "root_path": "/tmp",
            "root_id": "/tmp",
            "file_type": "python",
            "extension": ".py",
            "metadata_version": 2,
            "indexed_at": old_timestamp,
        },
    })
    return store


def _make_fake_ctx(pipeline):
    """Create a fake context for index_codebase calls."""
    async def fake_error(msg):
        pass

    class FakeLifespanContext:
        def __init__(self, pipeline):
            self.pipeline = pipeline

    class FakeRequestContext:
        def __init__(self, lifespan_context):
            self.lifespan_context = lifespan_context

    class FakeCtx:
        def __init__(self, pipeline):
            self.request_context = FakeRequestContext(FakeLifespanContext(pipeline))
            self.error = fake_error

    return FakeCtx(pipeline)


def test_dry_run_force_false_stale_root_has_stale_since():
    """Test 1: dry_run=True, force=False on a stale root → response status contains stale_since and staleness_message."""
    async def _run():
        store = await _create_stale_store_old_timestamp()
        config = Config()
        config.reconcile_on_startup = False
        config.stale_index_threshold_days = 7
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()

        try:
            ctx = _make_fake_ctx(pipeline)

            # Use /tmp which should resolve fine
            result = await index_codebase("/tmp", ctx, recursive=True, force=False, dry_run=True)

            assert result["success"] is True
            assert result["dry_run"] is True
            assert "status" in result
            # Status should contain stale_since and staleness_message
            assert "stale_since" in result["status"]
            assert "staleness_message" in result["status"]
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_dry_run_force_true_stale_root_no_stale_since():
    """Test 2: dry_run=True, force=True on the same stale root → response status contains NEITHER key."""
    async def _run():
        store = await _create_stale_store_old_timestamp()
        config = Config()
        config.reconcile_on_startup = False
        config.stale_index_threshold_days = 7
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()

        try:
            ctx = _make_fake_ctx(pipeline)

            result = await index_codebase("/tmp", ctx, recursive=True, force=True, dry_run=True)

            assert result["success"] is True
            assert result["dry_run"] is True
            assert "status" in result
            # Status should NOT contain stale_since or staleness_message when force=True
            assert "stale_since" not in result["status"]
            assert "staleness_message" not in result["status"]
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_non_dry_run_force_true_stale_root_status_before_no_stale_since():
    """Test 3: dry_run=False, force=True on the same stale root → status_before contains NEITHER key."""
    async def _run():
        store = await _create_stale_store_old_timestamp()
        config = Config()
        config.reconcile_on_startup = False
        config.stale_index_threshold_days = 7
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()

        try:
            ctx = _make_fake_ctx(pipeline)

            # Stub index_directory to return canned results without actual embedding
            async def fake_index_directory(*args, **kwargs):
                return []

            pipeline.index_directory = fake_index_directory

            result = await index_codebase("/tmp", ctx, recursive=True, force=True, dry_run=False)

            assert result["success"] is True
            assert result["indexed"] is True
            # status_before should NOT contain stale_since or staleness_message when force=True
            assert "stale_since" not in result["status_before"]
            assert "staleness_message" not in result["status_before"]
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_non_dry_run_force_false_stale_root_has_stale_since():
    """Test 4: dry_run=False, force=False on a stale root → stale_since still present (early return branch)."""
    async def _run():
        store = await _create_stale_store_old_timestamp()
        config = Config()
        config.reconcile_on_startup = False
        config.stale_index_threshold_days = 7
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()

        try:
            ctx = _make_fake_ctx(pipeline)

            result = await index_codebase("/tmp", ctx, recursive=True, force=False, dry_run=False)

            assert result["success"] is True
            assert result["indexed"] is False
            # Status should contain stale_since and staleness_message
            assert "stale_since" in result["status"]
            assert "staleness_message" in result["status"]
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_t04_no_timestamp_metadata_force_true_suppresses_stale_since():
    """Test 5: T04 scenario - root with NO indexed_at field. get_indexing_status yields stale_since, but index_codebase(force=True) suppresses it."""
    async def _run():
        store = await _create_stale_store_no_timestamps()
        config = Config()
        config.reconcile_on_startup = False
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()

        try:
            # First, verify get_indexing_status directly yields stale_since
            status = await pipeline.get_indexing_status("/tmp")
            assert "stale_since" in status
            assert "staleness_message" in status
            assert status["staleness_message"] == "Index has no timestamp metadata; treating as stale for safety"

            # Now verify index_codebase(force=True, dry_run=True) suppresses it
            ctx = _make_fake_ctx(pipeline)

            result = await index_codebase("/tmp", ctx, recursive=True, force=True, dry_run=True)

            assert result["success"] is True
            assert result["dry_run"] is True
            assert "status" in result
            # Status should NOT contain stale_since or staleness_message when force=True
            assert "stale_since" not in result["status"]
            assert "staleness_message" not in result["status"]
        finally:
            await pipeline.close()

    asyncio.run(_run())


def test_t04_no_timestamp_metadata_force_false_has_stale_since():
    """Test 6: T04 scenario - root with NO indexed_at field. force=False preserves stale_since."""
    async def _run():
        store = await _create_stale_store_no_timestamps()
        config = Config()
        config.reconcile_on_startup = False
        pipeline = RAGPipeline(config=config, vector_store=store)
        await pipeline.initialize()

        try:
            ctx = _make_fake_ctx(pipeline)

            result = await index_codebase("/tmp", ctx, recursive=True, force=False, dry_run=True)

            assert result["success"] is True
            assert result["dry_run"] is True
            assert "status" in result
            # Status should contain stale_since and staleness_message
            assert "stale_since" in result["status"]
            assert "staleness_message" in result["status"]
            assert result["status"]["staleness_message"] == "Index has no timestamp metadata; treating as stale for safety"
        finally:
            await pipeline.close()

    asyncio.run(_run())
