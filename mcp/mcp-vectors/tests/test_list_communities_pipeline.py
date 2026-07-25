"""Tests for RAGPipeline.list_communities (ADR-24, tickets 03-04)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from vectors.qdrant import CollectionMissingError


def _make_pipeline():
    """Minimal RAGPipeline with all external deps mocked out."""
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
    config.entity_search_limit = 20
    config.community_cap_ratio = 0.3
    config.targeting_log_full_query = False
    config.query_log_max_chars = 64

    lm_client = AsyncMock()
    lm_client.embedding_dimension = 4

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = config
    pipeline.lm_client = lm_client
    pipeline.vector_store = AsyncMock()
    pipeline._initialized = True
    pipeline._extraction_cache = MagicMock()
    pipeline.lock_manager = MagicMock()
    pipeline.safety = MagicMock()
    pipeline.parser = MagicMock()
    pipeline._graph_store = MagicMock()
    pipeline._communities = AsyncMock()
    pipeline._qdrant_entities = None
    pipeline._community_orchestrator = None
    pipeline._closing = False

    return pipeline


# ---------------------------------------------------------------------------
# 1. Missing root -> CommunitiesError
# ---------------------------------------------------------------------------


def test_list_communities_missing_root():
    """list_communities returns CommunitiesError when root not indexed."""

    async def _run():
        from vectors.community_results import CommunitiesError

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = False

        result = await pipeline.list_communities("/nonexistent/root")

        assert isinstance(result, CommunitiesError)
        d = result.to_dict()
        assert d["mode"] == "error"
        assert d["error"]["code"] == "root_not_indexed"
        assert "not indexed" in d["error"]["message"].lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. Dirty root -> CommunitiesRebuilding
# ---------------------------------------------------------------------------


def test_list_communities_dirty_root():
    """list_communities returns CommunitiesRebuilding when communities dirty."""

    async def _run():
        from vectors.community_results import CommunitiesRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = True

        schedule_calls = []
        pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)

        result = await pipeline.list_communities("/root/path")

        assert isinstance(result, CommunitiesRebuilding)
        assert result.reason == "Communities are being rebuilt"
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. No committed build -> CommunitiesRebuilding
# ---------------------------------------------------------------------------


def test_list_communities_no_committed_build():
    """list_communities returns CommunitiesRebuilding when no committed build."""

    async def _run():
        from vectors.community_results import CommunitiesRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = None

        schedule_calls = []
        pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)

        result = await pipeline.list_communities("/root/path")

        assert isinstance(result, CommunitiesRebuilding)
        assert result.reason == "Communities are being built for the first time"
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. Committed build exists -> CommunitiesReady
# ---------------------------------------------------------------------------


def test_list_communities_committed_build():
    """list_communities returns CommunitiesReady when committed build exists."""

    async def _run():
        from vectors.community_results import CommunitiesReady

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (3, "build-abc")

        communities_data = [
            {"community_id": "c1", "level": 0, "summary": "Test community"},
            {"community_id": "c2", "level": 1, "summary": "Nested community"},
        ]
        pipeline._communities.list_by_root = AsyncMock(return_value=communities_data)

        schedule_calls = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: schedule_calls.append(rid)

        result = await pipeline.list_communities("/root/path", level=0, limit=50)

        assert isinstance(result, CommunitiesReady)
        assert result.communities == communities_data
        assert len(schedule_calls) == 1
        pipeline._communities.list_by_root.assert_called_once_with(
            root_id="/root/path",
            committed_version=3,
            committed_build_id="build-abc",
            level=0,
            limit=50,
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Collection missing -> CommunitiesRebuilding
# ---------------------------------------------------------------------------


def test_list_communities_collection_missing():
    """list_communities returns CommunitiesRebuilding when collection missing."""

    async def _run():
        from vectors.community_results import CommunitiesRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (2, "build-xyz")

        pipeline._communities.list_by_root = AsyncMock(
            side_effect=CollectionMissingError("/root/path")
        )

        schedule_calls = []
        pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)

        result = await pipeline.list_communities("/root/path")

        assert isinstance(result, CommunitiesRebuilding)
        assert result.reason == "Community collection missing; rebuilding"
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. to_dict() shapes are correct
# ---------------------------------------------------------------------------


def test_list_communities_ready_to_dict():
    """CommunitiesReady.to_dict() produces correct wire shape."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-1")

        communities_data = [{"community_id": "c1", "level": 0}]
        pipeline._communities.list_by_root = AsyncMock(return_value=communities_data)
        pipeline.schedule_reports = MagicMock()

        result = await pipeline.list_communities("/root")
        d = result.to_dict()

        assert d["mode"] == "ready"
        assert d["communities"] == communities_data
        assert "success" not in d

    asyncio.run(_run())


def test_list_communities_rebuilding_to_dict():
    """CommunitiesRebuilding.to_dict() produces correct wire shape."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = True
        pipeline.schedule_detection = MagicMock()

        result = await pipeline.list_communities("/root")
        d = result.to_dict()

        assert d["mode"] == "rebuilding"
        assert "warning" in d
        assert "success" not in d

    asyncio.run(_run())


def test_list_communities_error_to_dict():
    """CommunitiesError.to_dict() produces correct wire shape."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = False

        result = await pipeline.list_communities("/root")
        d = result.to_dict()

        assert d["mode"] == "error"
        assert "error" in d
        assert d["error"]["code"] == "root_not_indexed"
        assert "success" not in d

    asyncio.run(_run())
