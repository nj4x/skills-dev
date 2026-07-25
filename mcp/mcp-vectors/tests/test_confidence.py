"""Tests for RAGPipeline._compute_confidence and search() confidence embedding."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vectors.qdrant import SearchResult
from vectors.rag import GraphificationStats, RAGPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_result() -> SearchResult:
    return SearchResult(
        id="chunk-1",
        score=0.9,
        file_path="/tmp/test.py",
        file_name="test.py",
        chunk_id=1,
        chunk_text="def foo(): pass",
        start_char=0,
        end_char=16,
        metadata={},
    )


def _make_pipeline() -> RAGPipeline:
    """Build a minimally wired RAGPipeline without real connections."""
    from vectors.config import Config
    config = Config()
    # Patch LMStudioClient and QdrantVectorStore so __init__ doesn't connect
    lm = MagicMock()
    lm.embedding_model = "test-embed"
    lm.llm_model = "test-llm"
    lm.embedding_dimension = 768
    lm._llm_model = "test-llm"
    vs = MagicMock()
    pipeline = RAGPipeline(config, lm_client=lm, vector_store=vs)
    return pipeline


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_confidence_no_entity_extraction():
    """When ENTITY_EXTRACTION is disabled, confidence level is always 'full'."""
    pipeline = _make_pipeline()

    with patch("vectors.rag.ENTITY_EXTRACTION", False):
        result = pipeline._compute_confidence("some-root-id")

    assert result["level"] == "full"
    assert result["reason"] == "graph_disabled"


def test_confidence_pending_extractions():
    """When stats show files_pending_extraction > 0, level is 'partial'."""
    pipeline = _make_pipeline()
    root_id = "test-root"
    stats = pipeline._get_or_create_stats(root_id)
    stats.files_pending_extraction = 3

    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline._compute_confidence(root_id)

    assert result["level"] == "partial"
    assert "3" in result["reason"]


def test_confidence_community_building():
    """When community_build_phase is 'detecting', level is 'partial'."""
    pipeline = _make_pipeline()
    root_id = "test-root"
    stats = pipeline._get_or_create_stats(root_id)
    stats.files_pending_extraction = 0
    stats.community_build_phase = "detecting"

    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline._compute_confidence(root_id)

    assert result["level"] == "partial"
    assert "detecting" in result["reason"]


def test_confidence_graph_ready():
    """When pending=0 and phase='ready', level is 'full'."""
    pipeline = _make_pipeline()
    root_id = "test-root"
    stats = pipeline._get_or_create_stats(root_id)
    stats.files_pending_extraction = 0
    stats.community_build_phase = "ready"

    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline._compute_confidence(root_id)

    assert result["level"] == "full"
    assert result["reason"] == "graph_ready"


# ---------------------------------------------------------------------------
# search() confidence embedding tests
# ---------------------------------------------------------------------------


def test_search_with_root_path_and_results_sets_confidence():
    """search() with root_path and results → confidence is a dict with 'level'."""
    async def _run():
        pipeline = _make_pipeline()
        pipeline._initialized = True
        result = _make_search_result()
        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
        pipeline.vector_store.search = AsyncMock(return_value=[result])
        pipeline._maybe_rerank_by_entity_graph = AsyncMock(return_value=[result])

        with patch("vectors.rag.ENTITY_EXTRACTION", False):
            response = await pipeline.search("query", root_path="/tmp")

        assert response.success is True
        assert response.confidence is not None
        assert "level" in response.confidence

    asyncio.run(_run())


def test_search_with_root_path_and_zero_results_sets_confidence():
    """search() with root_path and zero results → confidence is a dict (early-return branch)."""
    async def _run():
        pipeline = _make_pipeline()
        pipeline._initialized = True
        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
        pipeline.vector_store.search = AsyncMock(return_value=[])

        with patch("vectors.rag.ENTITY_EXTRACTION", False):
            response = await pipeline.search("query", root_path="/tmp")

        assert response.success is True
        assert response.confidence is not None
        assert "level" in response.confidence

    asyncio.run(_run())


@pytest.mark.parametrize("returns_results", [False, True], ids=["zero-results", "with-results"])
def test_search_with_no_root_path_confidence_is_none(returns_results):
    """search() with root_path=None → confidence is None on both branches."""
    async def _run():
        pipeline = _make_pipeline()
        pipeline._initialized = True
        result = _make_search_result()
        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
        pipeline.vector_store.search = AsyncMock(
            return_value=[result] if returns_results else []
        )
        if returns_results:
            pipeline._maybe_rerank_by_entity_graph = AsyncMock(return_value=[result])

        with patch("vectors.rag.ENTITY_EXTRACTION", False):
            response = await pipeline.search("query", root_path=None)

        assert response.success is True
        assert response.confidence is None
        assert response.error is None

    asyncio.run(_run())


def test_search_error_path_confidence_is_none():
    """Error path (vector_store.search raises) → success is False, confidence is None."""
    async def _run():
        pipeline = _make_pipeline()
        pipeline._initialized = True
        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
        pipeline.vector_store.search = AsyncMock(side_effect=RuntimeError("store down"))

        with patch("vectors.rag.ENTITY_EXTRACTION", False):
            response = await pipeline.search("query", root_path="/tmp")

        assert response.success is False
        assert response.confidence is None

    asyncio.run(_run())


def test_search_with_entity_extraction_sets_partial_confidence():
    """search() with ENTITY_EXTRACTION=True and pending extractions → confidence level is 'partial'."""
    async def _run():
        from vectors.paths import PathPolicy

        pipeline = _make_pipeline()
        pipeline._initialized = True
        result = _make_search_result()
        root_path = "/test-root"
        root_id = PathPolicy.path_key(root_path)
        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
        pipeline.vector_store.search = AsyncMock(return_value=[result])
        pipeline._maybe_rerank_by_entity_graph = AsyncMock(return_value=[result])
        stats = pipeline._get_or_create_stats(root_id)
        stats.files_pending_extraction = 3

        with patch("vectors.rag.ENTITY_EXTRACTION", True):
            response = await pipeline.search("query", root_path=root_path)

        assert response.success is True
        assert response.confidence is not None
        assert response.confidence["level"] == "partial"
        assert "3" in response.confidence["reason"]

    asyncio.run(_run())


@pytest.mark.parametrize("returns_results", [False, True], ids=["zero-results", "with-results"])
def test_compute_confidence_raise_converts_search_to_error_response(returns_results):
    """_compute_confidence raise inside search()'s try → success=False, error set.

    ADR-0042: moving confidence computation inside search()'s try block deliberately
    widens the except handler's scope. This test pins that accepted behavior so a
    future change cannot silently reintroduce a swallowing guard.
    """
    async def _run():
        pipeline = _make_pipeline()
        pipeline._initialized = True
        pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
        result = _make_search_result()
        pipeline.vector_store.search = AsyncMock(
            return_value=[result] if returns_results else []
        )
        if returns_results:
            pipeline._maybe_rerank_by_entity_graph = AsyncMock(return_value=[result])
        pipeline._compute_confidence = MagicMock(side_effect=RuntimeError("conf failed"))

        with patch("vectors.rag.ENTITY_EXTRACTION", False):
            response = await pipeline.search("query", root_path="/tmp")

        assert response.success is False
        assert response.error is not None
        assert "conf failed" in response.error

    asyncio.run(_run())
