"""Behavioral unit tests for RAGPipeline graph-seam methods (ADR-0002).

Covers find_entities, get_neighbors, get_callers:
- RuntimeError when ENTITY_EXTRACTION=False
- KeyError when root is not indexed
- Happy-path delegation to _graph_store
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_pipeline():
    from vectors.rag import RAGPipeline

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline._closing = False
    pipeline._community_orchestrator = None
    gs = MagicMock()
    gs.has_root.return_value = True
    pipeline._graph_store = gs
    return pipeline


# ---------------------------------------------------------------------------
# find_entities
# ---------------------------------------------------------------------------


def test_find_entities_raises_when_extraction_disabled():
    pipeline = _make_pipeline()
    with patch("vectors.rag.ENTITY_EXTRACTION", False):
        try:
            pipeline.find_entities("/root", "query")
            assert False, "Expected RuntimeError"
        except RuntimeError as e:
            assert "ENTITY_EXTRACTION" in str(e)


def test_find_entities_raises_key_error_when_root_not_indexed():
    pipeline = _make_pipeline()
    pipeline._graph_store.has_root.return_value = False
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        try:
            pipeline.find_entities("/root", "query")
            assert False, "Expected KeyError"
        except KeyError:
            pass


def test_find_entities_delegates_to_graph_store():
    pipeline = _make_pipeline()
    pipeline._graph_store.find_entities.return_value = [{"name": "Foo"}]
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline.find_entities("/root", "Foo", limit=5)
    assert result == [{"name": "Foo"}]
    pipeline._graph_store.find_entities.assert_called_once()


def test_find_entities_raises_key_error_when_graph_store_none():
    pipeline = _make_pipeline()
    pipeline._graph_store = None
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        try:
            pipeline.find_entities("/root", "query")
            assert False, "Expected KeyError"
        except KeyError:
            pass


# ---------------------------------------------------------------------------
# get_neighbors
# ---------------------------------------------------------------------------


def test_get_neighbors_raises_when_extraction_disabled():
    pipeline = _make_pipeline()
    with patch("vectors.rag.ENTITY_EXTRACTION", False):
        try:
            pipeline.get_neighbors("/root", "Foo")
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_get_neighbors_raises_key_error_when_root_not_indexed():
    pipeline = _make_pipeline()
    pipeline._graph_store.has_root.return_value = False
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        try:
            pipeline.get_neighbors("/root", "Foo")
            assert False, "Expected KeyError"
        except KeyError:
            pass


def test_get_neighbors_returns_entity_not_found_when_no_match():
    pipeline = _make_pipeline()
    pipeline._graph_store.find_entities.return_value = []
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline.get_neighbors("/root", "Ghost")
    assert result["entity"] is None
    assert result["neighbors"] == []
    assert "Ghost" in result["message"]


def test_get_neighbors_delegates_to_graph_store():
    pipeline = _make_pipeline()
    entity = {"id": "e1", "name": "Foo"}
    pipeline._graph_store.find_entities.return_value = [entity]
    pipeline._graph_store.get_neighbors.return_value = [{"id": "e2"}]
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline.get_neighbors("/root", "Foo", max_depth=1)
    assert result["entity"] == entity
    assert result["neighbors"] == [{"id": "e2"}]
    pipeline._graph_store.get_neighbors.assert_called_once_with("e1", max_depth=1, edge_types=None)


# ---------------------------------------------------------------------------
# get_callers
# ---------------------------------------------------------------------------


def test_get_callers_raises_when_extraction_disabled():
    pipeline = _make_pipeline()
    with patch("vectors.rag.ENTITY_EXTRACTION", False):
        try:
            pipeline.get_callers("/root", "Foo")
            assert False, "Expected RuntimeError"
        except RuntimeError:
            pass


def test_get_callers_raises_key_error_when_root_not_indexed():
    pipeline = _make_pipeline()
    pipeline._graph_store.has_root.return_value = False
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        try:
            pipeline.get_callers("/root", "Foo")
            assert False, "Expected KeyError"
        except KeyError:
            pass


def test_get_callers_delegates_to_graph_store():
    pipeline = _make_pipeline()
    pipeline._graph_store.get_callers.return_value = [{"caller": "bar"}]
    with patch("vectors.rag.ENTITY_EXTRACTION", True):
        result = pipeline.get_callers("/root", "Foo")
    assert result == [{"caller": "bar"}]
    pipeline._graph_store.get_callers.assert_called_once()
