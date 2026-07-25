"""
Phase 3-Pre blocker regression tests for rag.py features (B2, B6).

Tests for B2 (collection recovery) have been moved to test_community_orchestrator.py
following the ADR-0001 extraction of CommunityOrchestrator.  Only the B6 rerank stub
and the Fix-5 remove_document dispatching test remain here.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline():
    """Minimal RAGPipeline with all external deps mocked."""
    from vectors.rag import RAGPipeline
    from vectors.config import Config

    config = MagicMock(spec=Config)
    config.lm_studio_url = "http://localhost:1234/v1"
    config.embedding_model = "test"
    config.llm_model = "test"
    config.embedding_batch_size = 16
    config.qdrant_url = None
    config.qdrant_collection = "test"
    config.max_scroll_points = 1000
    config.scroll_page_size = 100

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = config
    pipeline.lm_client = AsyncMock()
    pipeline.lm_client.embedding_dimension = 4
    pipeline.vector_store = AsyncMock()
    pipeline._initialized = True
    pipeline._extraction_cache = MagicMock()
    pipeline.lock_manager = MagicMock()
    pipeline.safety = MagicMock()
    pipeline.parser = MagicMock()
    pipeline._graph_store = MagicMock()
    pipeline._graph_store.complete_community_build.return_value = True
    pipeline._graph_store.fail_community_build.return_value = (True, False)
    pipeline._communities = AsyncMock()
    pipeline._community_orchestrator = None
    pipeline._closing = False

    return pipeline


# ---------------------------------------------------------------------------
# B6 — rerank stub
# ---------------------------------------------------------------------------


def test_rerank_stub_returns_input_unchanged():
    """B6 — _maybe_rerank_by_entity_graph returns results unchanged when root_id=None (early exit)."""
    pipeline = _make_pipeline()

    fake_results = [object(), object(), object()]
    returned = asyncio.run(pipeline._maybe_rerank_by_entity_graph(fake_results, "", None))

    assert returned is fake_results, (
        "_maybe_rerank_by_entity_graph should return its input list unchanged (root_id=None early exit)"
    )


def test_rerank_stub_handles_empty_input():
    """B6 — handles empty results without error."""
    pipeline = _make_pipeline()
    assert asyncio.run(pipeline._maybe_rerank_by_entity_graph([], "", None)) == []


# ---------------------------------------------------------------------------
# Fix 5 — remove_document uses asyncio.to_thread for graph cleanup
# ---------------------------------------------------------------------------


def test_remove_document_delete_entities_is_awaitable():
    """Fix 5 — delete_file_entities in remove_document must not block the event loop.

    Verifies the call is dispatched via asyncio.to_thread by patching the module-level
    ENTITY_EXTRACTION flag, the directory scan, sqlite3.connect, and asyncio.to_thread.
    """
    from unittest.mock import patch
    from pathlib import Path

    async def _run():
        pipeline = _make_pipeline()

        def fake_delete(path_key, rid):
            return 1

        pipeline._graph_store.delete_file_entities = fake_delete
        pipeline.schedule_community_rebuild = MagicMock()

        dispatched_fns: list = []

        async def spy_to_thread(fn, *args, **kwargs):
            dispatched_fns.append(fn)
            return fn(*args, **kwargs)

        fake_row = MagicMock()
        fake_conn = MagicMock()
        fake_conn.execute.return_value.fetchall.return_value = [fake_row]
        fake_conn.close = MagicMock()

        with (
            patch("vectors.rag.ENTITY_EXTRACTION", True),
            patch("vectors.rag.GRAPH_DB_DIR", "/fake/graphdb"),
            patch("vectors.rag.resolve_path", return_value=Path("/some/file.py")),
            patch("os.path.isdir", return_value=True),
            patch("os.listdir", return_value=["testroot_graph.sqlite"]),
            patch("sqlite3.connect", return_value=fake_conn),
            patch("asyncio.to_thread", side_effect=spy_to_thread),
        ):
            await pipeline.remove_document("/some/file.py")

        assert fake_delete in dispatched_fns, (
            "delete_file_entities was not dispatched via asyncio.to_thread in remove_document"
        )

    asyncio.run(_run())
