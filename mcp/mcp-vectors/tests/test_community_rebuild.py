"""
Tests for RAGPipeline.schedule_community_rebuild (thin delegator to CommunityOrchestrator)
and close() community orchestrator teardown.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_pipeline():
    """Return a minimal RAGPipeline with a mock CommunityOrchestrator."""
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
    pipeline.vector_store = AsyncMock()
    pipeline._initialized = True
    pipeline._extraction_cache = MagicMock()
    pipeline.lock_manager = MagicMock()
    pipeline.safety = MagicMock()
    pipeline.parser = MagicMock()
    pipeline._graph_store = MagicMock()
    pipeline._communities = AsyncMock()
    pipeline._closing = False

    mock_orchestrator = MagicMock()
    mock_orchestrator._tasks = {}
    mock_orchestrator.drain = AsyncMock()
    pipeline._community_orchestrator = mock_orchestrator

    return pipeline, mock_orchestrator


# ---------------------------------------------------------------------------
# schedule_community_rebuild delegation
# ---------------------------------------------------------------------------


def test_schedule_community_rebuild_delegates():
    """schedule_community_rebuild is a deprecated alias that now drives the
    detection phase only (reports are lazy). It must delegate to
    orchestrator.schedule_detection(), not the legacy combined schedule()."""
    pipeline, orch = _make_pipeline()
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        pipeline.schedule_community_rebuild("r1")
    orch.schedule_detection.assert_called_once_with("r1")
    orch.schedule.assert_not_called()


def test_schedule_community_rebuild_no_op_when_closing():
    pipeline, orch = _make_pipeline()
    pipeline._closing = True
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        pipeline.schedule_community_rebuild("r1")
    orch.schedule.assert_not_called()


def test_schedule_community_rebuild_no_op_when_entity_extraction_disabled():
    pipeline, orch = _make_pipeline()
    with patch("vectors.rag.ENTITY_EXTRACTION", False):
        pipeline.schedule_community_rebuild("r1")
    orch.schedule.assert_not_called()


def test_schedule_community_rebuild_no_op_when_orchestrator_none():
    pipeline, _ = _make_pipeline()
    pipeline._community_orchestrator = None
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        pipeline.schedule_community_rebuild("r1")


# ---------------------------------------------------------------------------
# close(): orchestrator teardown
# ---------------------------------------------------------------------------


def test_close_signals_orchestrator_and_marks_closed():
    """close() calls orchestrator.close(), drains tasks, and marks pipeline as closed."""

    async def _run():
        pipeline, orch = _make_pipeline()
        orch._tasks = {}

        pipeline._communities.close = AsyncMock()
        pipeline.lm_client.close = AsyncMock()
        pipeline.vector_store.close = AsyncMock()

        await pipeline.close()

        orch.close.assert_called_once()
        assert pipeline._closing is True
        assert not pipeline._initialized

    asyncio.run(_run())


def test_close_calls_qdrant_entities_close():
    """close() must call _qdrant_entities.close() to avoid leaking the HTTP client."""

    async def _run():
        pipeline, orch = _make_pipeline()
        orch._tasks = {}

        pipeline._communities.close = AsyncMock()
        pipeline.lm_client.close = AsyncMock()
        pipeline.vector_store.close = AsyncMock()

        qdrant_entities_mock = AsyncMock()
        qdrant_entities_mock.close = AsyncMock()
        pipeline._qdrant_entities = qdrant_entities_mock

        await pipeline.close()

        qdrant_entities_mock.close.assert_called_once()

    asyncio.run(_run())
