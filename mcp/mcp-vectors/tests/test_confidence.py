"""Tests for RAGPipeline._compute_confidence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vectors.rag import GraphificationStats, RAGPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
