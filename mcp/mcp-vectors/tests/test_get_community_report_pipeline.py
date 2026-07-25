"""Tests for RAGPipeline.get_community_report (ADR-24, ticket 04)."""

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
    pipeline._reports_incomplete = {}

    return pipeline


# ---------------------------------------------------------------------------
# 1. Missing root -> CommunityReportError
# ---------------------------------------------------------------------------


def test_get_community_report_missing_root():
    """get_community_report returns CommunityReportError when root not indexed."""

    async def _run():
        from vectors.community_results import CommunityReportError

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = False

        result = await pipeline.get_community_report("/nonexistent/root", "c1")

        assert isinstance(result, CommunityReportError)
        d = result.to_dict()
        assert d["mode"] == "error"
        assert d["error"]["code"] == "root_not_indexed"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. Dirty root -> CommunityReportRebuilding
# ---------------------------------------------------------------------------


def test_get_community_report_dirty_root():
    """get_community_report returns CommunityReportRebuilding when communities dirty."""

    async def _run():
        from vectors.community_results import CommunityReportRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = True

        schedule_calls = []
        pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)

        result = await pipeline.get_community_report("/root/path", "c1")

        assert isinstance(result, CommunityReportRebuilding)
        assert result.reason == "Communities are being rebuilt"
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. No committed build -> CommunityReportRebuilding
# ---------------------------------------------------------------------------


def test_get_community_report_no_committed_build():
    """get_community_report returns CommunityReportRebuilding when no committed build."""

    async def _run():
        from vectors.community_results import CommunityReportRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = None

        schedule_calls = []
        pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)

        result = await pipeline.get_community_report("/root/path", "c1")

        assert isinstance(result, CommunityReportRebuilding)
        assert result.reason == "Communities are being built for the first time"
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. Reports rebuilding -> CommunityReportRebuilding
# ---------------------------------------------------------------------------


def test_get_community_report_reports_rebuilding():
    """get_community_report returns CommunityReportRebuilding when reports rebuilding."""

    async def _run():
        from vectors.community_results import CommunityReportRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-abc")
        pipeline._graph_store.report_build_status.return_value = MagicMock(
            committed_build_id="build-old",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        schedule_calls = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: schedule_calls.append(rid)

        result = await pipeline.get_community_report("/root/path", "c1")

        assert isinstance(result, CommunityReportRebuilding)
        assert "reports are being generated" in result.reason.lower()
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Community found -> CommunityReportReady
# ---------------------------------------------------------------------------


def test_get_community_report_found():
    """get_community_report returns CommunityReportReady when report found."""

    async def _run():
        from vectors.community_results import CommunityReportReady

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (2, "build-xyz")
        pipeline._graph_store.report_build_status.return_value = MagicMock(
            committed_build_id="build-xyz",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        mock_report = {"community_id": "c1", "summary": "Test community", "level": 0}
        pipeline._communities.get_by_id = AsyncMock(return_value=mock_report)

        schedule_calls = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: schedule_calls.append(rid)

        result = await pipeline.get_community_report("/root/path", "c1")

        assert isinstance(result, CommunityReportReady)
        assert result.report == mock_report
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. Community not found -> CommunityReportError
# ---------------------------------------------------------------------------


def test_get_community_report_not_found():
    """get_community_report returns CommunityReportError when report not found."""

    async def _run():
        from vectors.community_results import CommunityReportError

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-abc")
        pipeline._graph_store.report_build_status.return_value = MagicMock(
            committed_build_id="build-abc",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline._communities.get_by_id = AsyncMock(return_value=None)

        result = await pipeline.get_community_report("/root/path", "nonexistent")

        assert isinstance(result, CommunityReportError)
        assert result.error["code"] == "community_not_found"
        assert "nonexistent" in result.error["message"]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. Collection missing -> CommunityReportRebuilding
# ---------------------------------------------------------------------------


def test_get_community_report_collection_missing():
    """get_community_report returns CommunityReportRebuilding when collection missing."""

    async def _run():
        from vectors.community_results import CommunityReportRebuilding

        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-abc")
        pipeline._graph_store.report_build_status.return_value = MagicMock(
            committed_build_id="build-abc",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline._communities.get_by_id = AsyncMock(
            side_effect=CollectionMissingError("/root/path")
        )

        schedule_calls = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: schedule_calls.append(rid)

        result = await pipeline.get_community_report("/root/path", "c1")

        assert isinstance(result, CommunityReportRebuilding)
        assert "collection missing" in result.reason.lower()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. to_dict() shapes
# ---------------------------------------------------------------------------


def test_get_community_report_ready_to_dict():
    """CommunityReportReady.to_dict() produces correct wire shape."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-1")
        pipeline._graph_store.report_build_status.return_value = MagicMock(
            committed_build_id="build-1",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        mock_report = {"community_id": "c1"}
        pipeline._communities.get_by_id = AsyncMock(return_value=mock_report)
        pipeline.schedule_reports = MagicMock()

        result = await pipeline.get_community_report("/root", "c1")
        d = result.to_dict()

        assert d["mode"] == "ready"
        assert d["community"] == mock_report
        assert "success" not in d

    asyncio.run(_run())


def test_get_community_report_error_to_dict():
    """CommunityReportError.to_dict() produces correct wire shape."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = False

        result = await pipeline.get_community_report("/root", "c1")
        d = result.to_dict()

        assert d["mode"] == "error"
        assert "error" in d
        assert "success" not in d

    asyncio.run(_run())
