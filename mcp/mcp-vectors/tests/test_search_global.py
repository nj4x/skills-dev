"""
Tests for RAGPipeline.search_global (Phase 2D).

Covers:
- feature_disabled -> error code "feature_disabled"
- root not indexed -> error code "root_not_indexed"
- dirty root -> mode "rebuilding" with fallback_results
- CollectionMissingError -> mode "rebuilding"
- fresh generation -> mode "ready" with community_results + synthesis
- community_results sorted by score desc then community_id
- no committed_build_id -> triggers rebuild
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from vectors.graph_store import ReportBuildStatus
from vectors.qdrant import CollectionMissingError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    # Targeting config
    config.entity_search_limit = 20
    config.community_cap_ratio = 0.3
    config.targeting_log_full_query = False
    config.query_log_max_chars = 64

    lm_client = AsyncMock()
    lm_client.embedding_dimension = 4
    vector_store = AsyncMock()

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = config
    pipeline.lm_client = lm_client
    pipeline.vector_store = vector_store
    pipeline._initialized = True
    pipeline._extraction_cache = MagicMock()
    pipeline.lock_manager = MagicMock()
    pipeline.safety = MagicMock()
    pipeline.parser = MagicMock()
    pipeline._graph_store = MagicMock()
    pipeline._communities = AsyncMock()
    pipeline._qdrant_entities = None  # targeting disabled by default in base helper
    pipeline._community_orchestrator = None
    pipeline._closing = False

    return pipeline


def _make_pipeline_with_targeting():
    """Pipeline with _qdrant_entities wired as an AsyncMock for targeting tests."""
    pipeline = _make_pipeline()
    pipeline._qdrant_entities = AsyncMock()
    return pipeline


# ---------------------------------------------------------------------------
# 1. feature_disabled -> error code "feature_disabled"
# ---------------------------------------------------------------------------


def test_search_global_feature_disabled():
    """Returns feature_disabled error when ENTITY_EXTRACTION is False."""

    async def _run():
        pipeline = _make_pipeline()
        with patch("vectors.rag.ENTITY_EXTRACTION", False):
            result = await pipeline.search_global("query", "/some/root")
        assert result["success"] is False
        assert result["error"]["code"] == "feature_disabled"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. root not indexed -> error code "root_not_indexed"
# ---------------------------------------------------------------------------


def test_search_global_root_not_indexed():
    """Returns root_not_indexed when GraphStore.has_root returns False."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = False

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/some/root")

        assert result["success"] is False
        assert result["error"]["code"] == "root_not_indexed"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. dirty root -> mode "rebuilding" with fallback_results
# ---------------------------------------------------------------------------


def test_search_global_dirty_root_returns_fallback():
    """Dirty communities trigger rebuild + return vector fallback."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-abc")
        pipeline._graph_store.get_graph_version.return_value = 2
        pipeline._graph_store.are_communities_dirty.return_value = True

        fallback_payload = {
            "success": True, "query": "query", "response": "fallback", "sources": []
        }
        pipeline.search_with_response = AsyncMock(return_value=fallback_payload)

        schedule_calls = []

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            # Dirty detection state now schedules the (cheap) detection phase.
            pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)
            result = await pipeline.search_global("query", "/some/root", limit=5)

        assert result["success"] is True
        assert result["mode"] == "rebuilding"
        assert result["fallback_results"] == fallback_payload
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. CollectionMissingError -> mode "rebuilding"
# ---------------------------------------------------------------------------


def test_search_global_collection_missing_returns_fallback():
    """CollectionMissingError (after reports settled) triggers report rebuild
    + returns fallback."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-abc")
        pipeline._graph_store.get_graph_version.return_value = 1
        pipeline._graph_store.are_communities_dirty.return_value = False
        # Reports settled/committed for the current build so we reach the
        # community-search call (where the collection is then found missing).
        pipeline._graph_store.report_build_status.return_value = ReportBuildStatus(
            committed_build_id="build-abc",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
        pipeline._communities.search = AsyncMock(
            side_effect=CollectionMissingError("root1")
        )

        fallback_payload = {
            "success": True, "query": "query", "response": "fallback", "sources": []
        }
        pipeline.search_with_response = AsyncMock(return_value=fallback_payload)

        schedule_calls = []

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            pipeline.schedule_reports = lambda rid: schedule_calls.append(rid)
            result = await pipeline.search_global("query", "/some/root", limit=5)

        assert result["success"] is True
        assert result["mode"] == "rebuilding"
        assert "rebuilding" in result["warning"].lower()
        assert result["fallback_results"] == fallback_payload
        assert schedule_calls, "collection-missing path must schedule report regeneration"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. fresh generation -> mode "ready" with community_results + synthesis
# ---------------------------------------------------------------------------


def test_search_global_ready_mode():
    """Clean generation returns mode 'ready' with community_results and synthesis."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (3, "build-xyz")
        pipeline._graph_store.get_graph_version.return_value = 3
        pipeline._graph_store.are_communities_dirty.return_value = False
        # Reports fully committed for the current build → coverage "complete".
        pipeline._graph_store.report_build_status.return_value = ReportBuildStatus(
            committed_build_id="build-xyz",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

        community_hits = [
            {"community_id": "c1", "title": "T1", "summary": "S1", "score": 0.9},
            {"community_id": "c2", "title": "T2", "summary": "S2", "score": 0.7},
        ]
        pipeline._communities.search = AsyncMock(return_value=community_hits)
        pipeline.lm_client.generate_response = AsyncMock(return_value="synthesized answer")

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/some/root", limit=5)

        assert result["success"] is True
        assert result["mode"] == "ready"
        assert result["synthesis"] == "synthesized answer"
        assert len(result["community_results"]) == 2

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. community_results sorted by score desc then community_id asc
# ---------------------------------------------------------------------------


def test_search_global_community_results_sorted():
    """Results sorted by score descending, then community_id ascending."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-1")
        pipeline._graph_store.get_graph_version.return_value = 1
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.report_build_status.return_value = ReportBuildStatus(
            committed_build_id="build-1",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.0, 0.0, 0.0, 0.0])
        pipeline.lm_client.generate_response = AsyncMock(return_value="")

        community_hits = [
            {"community_id": "z1", "title": "", "summary": "", "score": 0.5},
            {"community_id": "a1", "title": "", "summary": "", "score": 0.9},
            {"community_id": "a2", "title": "", "summary": "", "score": 0.9},
            {"community_id": "m1", "title": "", "summary": "", "score": 0.3},
        ]
        pipeline._communities.search = AsyncMock(return_value=community_hits)

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/some/root", limit=10)

        ids = [r["community_id"] for r in result["community_results"]]
        assert ids == ["a1", "a2", "z1", "m1"], f"Wrong order: {ids}"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. no committed_build_id -> triggers rebuild even if not dirty
# ---------------------------------------------------------------------------


def test_search_global_no_build_id_triggers_rebuild():
    """If committed_build_id is None (not yet built), mode is rebuilding."""

    async def _run():
        pipeline = _make_pipeline()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (0, None)
        pipeline._graph_store.get_graph_version.return_value = 1
        pipeline._graph_store.are_communities_dirty.return_value = False

        fallback_payload = {"success": True, "query": "q", "response": "", "sources": []}
        pipeline.search_with_response = AsyncMock(return_value=fallback_payload)

        schedule_calls = []

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            pipeline.schedule_detection = lambda rid: schedule_calls.append(rid)
            result = await pipeline.search_global("q", "/root")

        assert result["mode"] == "rebuilding"
        assert len(schedule_calls) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. Targeting path — fresh reports → returns ready result with incomplete=True
# ---------------------------------------------------------------------------


def test_targeting_returns_ready_when_reports_are_fresh():
    """When entity search hits communities and all points exist → targeting returns ready."""

    async def _run():
        pipeline = _make_pipeline_with_targeting()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (2, "build-tgt")
        pipeline._graph_store.get_graph_version.return_value = 2
        pipeline._graph_store.are_communities_dirty.return_value = False

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

        # Entity search returns one hit
        pipeline._qdrant_entities.search = AsyncMock(
            return_value=[{"entity_id": "e1", "name": "Foo", "type": "func", "score": 0.9}]
        )

        # The entity maps to community "c1"
        pipeline._graph_store.get_community_ids_for_entities = MagicMock(return_value={"c1"})

        # Total communities = 10, targeted = 1 → well within 30% cap
        pipeline._graph_store.get_committed_community_ids = MagicMock(
            return_value=["c" + str(i) for i in range(10)]
        )

        # All targeted points exist in Qdrant
        pipeline._communities.all_points_exist = AsyncMock(return_value=True)

        community_hits = [
            {"community_id": "c1", "title": "T1", "summary": "S1", "score": 0.95}
        ]
        pipeline._communities.search_filtered = AsyncMock(return_value=community_hits)
        pipeline.lm_client.generate_response = AsyncMock(return_value="targeted synthesis")

        schedule_calls: list = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: schedule_calls.append(
            (rid, target_clusters)
        )

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/root", limit=5)

        assert result["success"] is True
        assert result["mode"] == "ready"
        assert result["incomplete"] is True  # targeting always returns incomplete=True
        assert result["synthesis"] == "targeted synthesis"
        assert len(result["community_results"]) == 1
        # schedule_reports must have been called with the targeted cluster list
        assert any(tc is not None and "c1" in tc for _, tc in schedule_calls)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 9. Targeting — zero entity hits → falls through to full summarization
# ---------------------------------------------------------------------------


def test_targeting_falls_through_on_zero_entity_hits():
    """No entity hits → targeting returns None → full schedule_reports path runs."""

    async def _run():
        pipeline = _make_pipeline_with_targeting()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-x")
        pipeline._graph_store.get_graph_version.return_value = 1
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.report_build_status.return_value = ReportBuildStatus(
            committed_build_id="build-x",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
        pipeline._qdrant_entities.search = AsyncMock(return_value=[])  # zero hits

        community_hits = [{"community_id": "c1", "title": "T", "summary": "S", "score": 0.8}]
        pipeline._communities.search = AsyncMock(return_value=community_hits)
        pipeline.lm_client.generate_response = AsyncMock(return_value="full synthesis")

        full_reports_calls: list = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: full_reports_calls.append(
            (rid, target_clusters)
        )

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/root", limit=5)

        # Full path ran → schedule_reports without target_clusters
        assert result["success"] is True
        assert result["mode"] == "ready"
        assert any(tc is None for _, tc in full_reports_calls)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 10. Targeting — cap exceeded → falls through to full summarization
# ---------------------------------------------------------------------------


def test_targeting_falls_through_when_cap_exceeded():
    """Targeting community count > cap ratio → full summarization path runs."""

    async def _run():
        pipeline = _make_pipeline_with_targeting()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-cap")
        pipeline._graph_store.get_graph_version.return_value = 1
        pipeline._graph_store.are_communities_dirty.return_value = False
        pipeline._graph_store.report_build_status.return_value = ReportBuildStatus(
            committed_build_id="build-cap",
            dirty=False,
            claimed_build_id=None,
            claim_expires_at=None,
        )

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

        # Entity search returns hits that map to 4 communities out of 10 (40% > 30% cap)
        pipeline._qdrant_entities.search = AsyncMock(
            return_value=[{"entity_id": f"e{i}", "name": f"E{i}", "type": "func", "score": 0.9}
                          for i in range(4)]
        )
        pipeline._graph_store.get_community_ids_for_entities = MagicMock(
            return_value={"c0", "c1", "c2", "c3"}  # 4 communities
        )
        pipeline._graph_store.get_committed_community_ids = MagicMock(
            return_value=["c" + str(i) for i in range(10)]  # 10 total → cap=3
        )

        community_hits = [{"community_id": "c0", "title": "T", "summary": "S", "score": 0.8}]
        pipeline._communities.search = AsyncMock(return_value=community_hits)
        pipeline.lm_client.generate_response = AsyncMock(return_value="fallback synthesis")

        schedule_calls: list = []
        pipeline.schedule_reports = lambda rid, target_clusters=None: schedule_calls.append(
            (rid, target_clusters)
        )

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/root", limit=5)

        assert result["success"] is True
        # Full path ran (mode may be "ready" or partial)
        assert result["mode"] in ("ready", "rebuilding")
        # schedule_reports called without target (full sweep)
        assert any(tc is None for _, tc in schedule_calls)
        # targeted path's all_points_exist must NOT have been called (fell through)
        pipeline._communities.assert_not_called()  # search_filtered not called

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 11. Targeting — not all reports fresh → returns rebuilding with fallback
# ---------------------------------------------------------------------------


def test_targeting_returns_rebuilding_when_not_all_reports_fresh():
    """If targeted reports not yet generated, returns mode=rebuilding with fallback."""

    async def _run():
        pipeline = _make_pipeline_with_targeting()
        pipeline._graph_store.has_root.return_value = True
        pipeline._graph_store.get_committed_generation.return_value = (1, "build-fresh")
        pipeline._graph_store.get_graph_version.return_value = 1
        pipeline._graph_store.are_communities_dirty.return_value = False

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

        pipeline._qdrant_entities.search = AsyncMock(
            return_value=[{"entity_id": "e1", "name": "Foo", "type": "func", "score": 0.9}]
        )
        pipeline._graph_store.get_community_ids_for_entities = MagicMock(return_value={"c1"})
        pipeline._graph_store.get_committed_community_ids = MagicMock(
            return_value=["c" + str(i) for i in range(10)]
        )

        # Reports not yet generated for this community
        pipeline._communities.all_points_exist = AsyncMock(return_value=False)

        fallback_payload = {"success": True, "query": "q", "response": "fb", "sources": []}
        pipeline.search_with_response = AsyncMock(return_value=fallback_payload)

        pipeline.schedule_reports = MagicMock()

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            result = await pipeline.search_global("query", "/root", limit=5)

        assert result["success"] is True
        assert result["mode"] == "rebuilding"
        assert result["incomplete"] is True
        assert "targeted" in result["warning"].lower()
        assert result["fallback_results"] == fallback_payload

    asyncio.run(_run())
