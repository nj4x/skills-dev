"""Tests for entity_names back-fill in _extract_and_merge (Phase 3 revision).

After async entity extraction completes, _extract_and_merge must:
1. Call annotate_chunks to populate chunk["entity_names"] on the in-memory doc.
2. Call vector_store.update_chunk_entities so already-stored Qdrant payloads carry
   the extracted entity names, enabling entity-graph reranking without a re-index.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pipeline(vector_store=None):
    """Minimal RAGPipeline built via __new__ — bypasses __init__ safely."""
    from vectors.rag import RAGPipeline

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = MagicMock()
    pipeline.lm_client = AsyncMock()
    pipeline.vector_store = vector_store or AsyncMock()
    pipeline._initialized = True
    pipeline._extraction_cache = MagicMock()
    pipeline.lock_manager = MagicMock()
    pipeline.safety = MagicMock()
    pipeline.parser = MagicMock()
    pipeline._graph_store = MagicMock()
    pipeline._communities = AsyncMock()
    pipeline._community_orchestrator = None
    pipeline._closing = False
    pipeline._graph_stats = {}
    return pipeline


def _make_doc(chunks=None):
    """Minimal document object with chunks list."""
    doc = MagicMock()
    doc.chunks = chunks if chunks is not None else [
        {"chunk_id": 0, "chunk_text": "Alice met Bob at the office."},
        {"chunk_id": 1, "chunk_text": "Bob works for ACME Corp."},
    ]
    return doc


def _make_entity_map(entities=None):
    """Minimal EntityMap with an entities list."""
    em = MagicMock()
    em.entities = entities or [MagicMock(name="Alice"), MagicMock(name="Bob")]
    return em


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_extract_and_merge_calls_update_chunk_entities():
    """_extract_and_merge must call vector_store.update_chunk_entities after extraction."""

    async def _run():
        vector_store = AsyncMock()
        vector_store.update_chunk_entities = AsyncMock()
        pipeline = _make_pipeline(vector_store=vector_store)

        doc = _make_doc()
        entity_map = _make_entity_map()
        file_path = Path("/tmp/test.py")

        # Stub EntityExtractor.extract_file to return our entity_map synchronously
        with patch("vectors.rag.EntityExtractor") as MockExtractor:
            mock_extractor_instance = AsyncMock()
            mock_extractor_instance.extract_file = AsyncMock(return_value=entity_map)
            MockExtractor.return_value = mock_extractor_instance

            # Stub annotate_chunks to avoid real logic but mark side-effect
            with patch("vectors.rag.annotate_chunks") as mock_annotate:
                # Stub asyncio.to_thread so _graph_store.replace_file_entity_map doesn't block
            # Must return (version, stubs) tuple
                with patch("asyncio.to_thread", new=AsyncMock(return_value=(1, [], []))):
                    # Stub _schedule_community_rebuild
                    pipeline.schedule_community_rebuild = MagicMock()

                    await pipeline._extract_and_merge(
                        file_path, doc, "root_id", "path_key"
                    )

                    # annotate_chunks must have been called with the doc and entity_map
                    mock_annotate.assert_called_once_with(doc, entity_map)

                    # update_chunk_entities must have been called with the file path and doc.chunks
                    vector_store.update_chunk_entities.assert_awaited_once_with(
                        str(file_path), doc.chunks
                    )

    asyncio.run(_run())


def test_extract_and_merge_backfill_failure_does_not_propagate():
    """Back-fill errors must be caught and logged — they must never crash extraction."""

    async def _run():
        vector_store = AsyncMock()
        vector_store.update_chunk_entities = AsyncMock(
            side_effect=RuntimeError("Qdrant unavailable")
        )
        pipeline = _make_pipeline(vector_store=vector_store)

        doc = _make_doc()
        entity_map = _make_entity_map()
        file_path = Path("/tmp/fail.py")

        with patch("vectors.rag.EntityExtractor") as MockExtractor:
            mock_extractor_instance = AsyncMock()
            mock_extractor_instance.extract_file = AsyncMock(return_value=entity_map)
            MockExtractor.return_value = mock_extractor_instance

            with patch("vectors.rag.annotate_chunks"):
                with patch("asyncio.to_thread", new=AsyncMock(return_value=(1, [], []))):
                    pipeline.schedule_community_rebuild = MagicMock()

                    # Must NOT raise — failure is swallowed with a warning
                    await pipeline._extract_and_merge(
                        file_path, doc, "root_id", "path_key"
                    )

        # The task still records a successful extraction despite back-fill failure
        stats = pipeline._graph_stats.get("root_id")
        assert stats is not None
        assert stats.files_extracted == 1

    asyncio.run(_run())


def test_extract_and_merge_stats_updated_after_backfill():
    """GraphificationStats must reflect extracted entities even when back-fill is used."""

    async def _run():
        vector_store = AsyncMock()
        vector_store.update_chunk_entities = AsyncMock()
        pipeline = _make_pipeline(vector_store=vector_store)

        chunks = [{"chunk_id": i, "chunk_text": f"chunk {i}"} for i in range(3)]
        doc = _make_doc(chunks=chunks)
        entity_map = _make_entity_map(entities=[MagicMock(), MagicMock(), MagicMock()])
        file_path = Path("/tmp/stats_test.py")

        with patch("vectors.rag.EntityExtractor") as MockExtractor:
            mock_extractor_instance = AsyncMock()
            mock_extractor_instance.extract_file = AsyncMock(return_value=entity_map)
            MockExtractor.return_value = mock_extractor_instance

            with patch("vectors.rag.annotate_chunks"):
                with patch("asyncio.to_thread", new=AsyncMock(return_value=(1, [], []))):
                    pipeline.schedule_community_rebuild = MagicMock()

                    await pipeline._extract_and_merge(
                        file_path, doc, "root_id", "path_key"
                    )

        stats = pipeline._graph_stats["root_id"]
        assert stats.files_extracted == 1
        assert stats.chunks_extracted == 3
        assert stats.entities_found == 3
        assert stats.files_pending_extraction == 0

    asyncio.run(_run())
