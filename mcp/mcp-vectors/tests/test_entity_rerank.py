"""
Tests for entity-graph reranking (_maybe_rerank_by_entity_graph Phase 3B).

These tests exercise the async implementation of _maybe_rerank_by_entity_graph.
All early-exit paths and the full blending logic are covered.
Integration tests 11-12 verify that search() forwards the right arguments.
"""
from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

from vectors.qdrant import SearchResult
from vectors.paths import PathPolicy


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
    pipeline._community_orchestrator = None
    pipeline._closing = False

    return pipeline


def _make_result(score: float, entity_names: list | None = None) -> SearchResult:
    """Create a minimal SearchResult for reranking tests."""
    meta: dict = {}
    if entity_names is not None:
        meta["entity_names"] = entity_names
    return SearchResult(
        id="test-id",
        score=score,
        file_path="/test/file.py",
        file_name="file.py",
        chunk_id=0,
        chunk_text="test chunk",
        start_char=0,
        end_char=10,
        metadata=meta,
    )


# ---------------------------------------------------------------------------
# 1. Alpha zero fast path
# ---------------------------------------------------------------------------


def test_alpha_zero_fast_path():
    """ENTITY_RERANK_ALPHA == 0.0 returns results unchanged without touching graph store."""
    pipeline = _make_pipeline()
    fake_results = [_make_result(0.9), _make_result(0.5)]

    with patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.0):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph(fake_results, "query", "root1")
        )

    assert returned is fake_results
    pipeline._graph_store.find_entities.assert_not_called()


# ---------------------------------------------------------------------------
# 2. No root_id → noop
# ---------------------------------------------------------------------------


def test_no_root_id_noop():
    """root_id=None returns input unchanged (equality check)."""
    pipeline = _make_pipeline()
    fake_results = [_make_result(0.8)]

    with patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph(fake_results, "query", None)
        )

    assert returned == fake_results


# ---------------------------------------------------------------------------
# 3. Entity extraction disabled → noop
# ---------------------------------------------------------------------------


def test_entity_extraction_disabled_noop():
    """ENTITY_EXTRACTION=False and _graph_store=None returns input unchanged."""
    pipeline = _make_pipeline()
    pipeline._graph_store = None
    fake_results = [_make_result(0.7)]

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", False),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph(fake_results, "query", "root1")
        )

    assert returned == fake_results


# ---------------------------------------------------------------------------
# 4. No matching entities → noop
# ---------------------------------------------------------------------------


def test_no_matching_entities_noop():
    """find_entities returning [] returns input unchanged."""
    pipeline = _make_pipeline()
    pipeline._graph_store.find_entities = MagicMock(return_value=[])
    fake_results = [_make_result(0.9)]

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph(fake_results, "query", "root1")
        )

    assert returned == fake_results


# ---------------------------------------------------------------------------
# 5. Blended score reorders results
# ---------------------------------------------------------------------------


def test_blended_score_reorders_results():
    """alpha=0.5: entity overlap promotes lower-vector result above higher-vector result."""
    pipeline = _make_pipeline()
    r1 = _make_result(score=0.9, entity_names=[])
    r2 = _make_result(score=0.4, entity_names=["foo"])
    pipeline._graph_store.find_entities = MagicMock(return_value=[{"name": "foo"}])

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph([r1, r2], "foo query", "root1")
        )

    # Expected blended scores:
    # r1: (1-0.5)*0.9 + 0.5*0   = 0.45
    # r2: (1-0.5)*0.4 + 0.5*1.0 = 0.70
    assert len(returned) == 2
    assert abs(returned[0].score - 0.70) < 1e-9, f"expected 0.70, got {returned[0].score}"
    assert abs(returned[1].score - 0.45) < 1e-9, f"expected 0.45, got {returned[1].score}"


# ---------------------------------------------------------------------------
# 6. Alpha one — pure entity scoring
# ---------------------------------------------------------------------------


def test_alpha_one_pure_entity():
    """alpha=1.0 makes entity overlap the sole ranking signal; vector score ignored."""
    pipeline = _make_pipeline()
    r1 = _make_result(score=0.9, entity_names=[])
    r2 = _make_result(score=0.1, entity_names=["bar"])
    pipeline._graph_store.find_entities = MagicMock(return_value=[{"name": "bar"}])

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 1.0),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph([r1, r2], "bar query", "root1")
        )

    assert len(returned) == 2
    # r2 entity_overlap=1.0 → blended = 0*0.1 + 1.0*1.0 = 1.0
    # r1 entity_overlap=0   → blended = 0*0.9 + 1.0*0   = 0.0
    assert returned[0].score == 1.0, f"expected 1.0, got {returned[0].score}"
    assert returned[1].score == 0.0, f"expected 0.0, got {returned[1].score}"


# ---------------------------------------------------------------------------
# 7. Missing entity_names key → no crash, entity score = 0
# ---------------------------------------------------------------------------


def test_missing_entity_names_key():
    """metadata={} (no entity_names key) yields entity_overlap=0 without crashing."""
    pipeline = _make_pipeline()
    r = _make_result(score=0.5)  # metadata={} — no entity_names key
    pipeline._graph_store.find_entities = MagicMock(return_value=[{"name": "x"}])

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph([r], "x query", "root1")
        )

    assert len(returned) == 1
    # chunk_names = frozenset() → overlap = 0
    # blended = 0.5*0.5 + 0.5*0 = 0.25
    assert abs(returned[0].score - 0.25) < 1e-9, f"expected 0.25, got {returned[0].score}"


# ---------------------------------------------------------------------------
# 8. Blended score replaces .score on returned result
# ---------------------------------------------------------------------------


def test_blended_score_replaces_result_score():
    """Returned result's .score is the blended value, not the original vector score."""
    pipeline = _make_pipeline()
    r = _make_result(score=0.8, entity_names=["foo"])
    pipeline._graph_store.find_entities = MagicMock(return_value=[{"name": "foo"}])

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph([r], "foo query", "root1")
        )

    assert len(returned) == 1
    # blended = 0.5*0.8 + 0.5*1.0 = 0.9
    assert abs(returned[0].score - 0.9) < 1e-9, f"expected 0.9, got {returned[0].score}"


# ---------------------------------------------------------------------------
# 9. Empty results noop
# ---------------------------------------------------------------------------


def test_empty_results_noop():
    """Empty results list is returned immediately without calling find_entities."""
    pipeline = _make_pipeline()

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph([], "query", "root1")
        )

    assert returned == []
    pipeline._graph_store.find_entities.assert_not_called()


# ---------------------------------------------------------------------------
# 10. Graph store error falls back to original results
# ---------------------------------------------------------------------------


def test_graph_store_error_falls_back():
    """sqlite3.OperationalError from find_entities returns original results and logs warning."""
    pipeline = _make_pipeline()
    fake_results = [_make_result(0.9)]
    pipeline._graph_store.find_entities = MagicMock(
        side_effect=sqlite3.OperationalError("disk I/O error")
    )

    with (
        patch("vectors.rag.ENTITY_RERANK_ALPHA", 0.5),
        patch("vectors.rag.ENTITY_EXTRACTION", True),
        patch("vectors.rag.logger") as mock_logger,
    ):
        returned = asyncio.run(
            pipeline._maybe_rerank_by_entity_graph(fake_results, "query", "root1")
        )

    assert returned is fake_results
    mock_logger.warning.assert_called()


# ---------------------------------------------------------------------------
# 11. Integration: search() passes query and root_id to reranker
# ---------------------------------------------------------------------------


def test_search_passes_query_and_root_id_to_reranker():
    """pipeline.search() calls _maybe_rerank_by_entity_graph with the correct query and root_id."""
    async def _run():
        pipeline = _make_pipeline()

        r1 = SearchResult(
            id="1", score=0.9, file_path="/test/a.py", file_name="a.py",
            chunk_id=0, chunk_text="text1", start_char=0, end_char=5, metadata={},
        )
        r2 = SearchResult(
            id="2", score=0.8, file_path="/test/b.py", file_name="b.py",
            chunk_id=0, chunk_text="text2", start_char=0, end_char=5, metadata={},
        )
        two_results = [r1, r2]

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.0, 0.0, 0.0, 0.0])
        pipeline.vector_store.search = AsyncMock(return_value=two_results)
        pipeline._maybe_rerank_by_entity_graph = AsyncMock(return_value=two_results)

        expected_root_id = PathPolicy.path_key("/some/root")

        await pipeline.search("my query", root_path="/some/root")

        pipeline._maybe_rerank_by_entity_graph.assert_awaited_once()
        call_args = pipeline._maybe_rerank_by_entity_graph.call_args
        # Called positionally: (results, query, root_id)
        assert call_args.args[1] == "my query"
        assert call_args.args[2] == expected_root_id

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 12. Integration: search() passes None root_id when root_path is None
# ---------------------------------------------------------------------------


def test_search_no_root_path_passes_none_root_id():
    """pipeline.search(root_path=None) passes root_id=None to _maybe_rerank_by_entity_graph."""
    async def _run():
        pipeline = _make_pipeline()

        r1 = SearchResult(
            id="1", score=0.9, file_path="/test/a.py", file_name="a.py",
            chunk_id=0, chunk_text="text1", start_char=0, end_char=5, metadata={},
        )
        one_result = [r1]

        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.0, 0.0, 0.0, 0.0])
        pipeline.vector_store.search = AsyncMock(return_value=one_result)
        pipeline._maybe_rerank_by_entity_graph = AsyncMock(return_value=one_result)

        await pipeline.search("my query", root_path=None)

        pipeline._maybe_rerank_by_entity_graph.assert_awaited_once()
        call_args = pipeline._maybe_rerank_by_entity_graph.call_args
        # Called positionally: (results, query, root_id)
        assert call_args.args[1] == "my query"
        assert call_args.args[2] is None

    asyncio.run(_run())
