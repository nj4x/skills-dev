"""Tests for entity-embedding upsert in _extract_and_merge.

Covers the two guarantees added for observability + correctness:

Test A — id-consistency: the entity_id passed to QdrantEntities.upsert equals
graph_store._entity_id(name, type, root_id), so entity-targeting community
lookups can resolve the point later.

Test B — sibling independence + enriched diagnostics: when one entity's upsert
raises, the sibling still gets upserted, exactly one enriched WARNING (with a
stack trace) is emitted per failure signature, a count-summary WARNING is
emitted, and stats.entities_embed_failed is incremented.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from vectors.entity_extractor import Entity
from vectors.graph_store import entity_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RecordingEntities:
    """Stand-in for RAGPipeline._qdrant_entities that records upsert kwargs.

    `fail_names` is a set of entity names for which upsert raises RuntimeError.
    """

    def __init__(self, fail_names: set[str] | None = None):
        self.calls: list[dict] = []
        self.fail_names = fail_names or set()

    async def upsert(self, **kwargs) -> None:
        if kwargs.get("name") in self.fail_names:
            raise RuntimeError("simulated qdrant failure")
        self.calls.append(kwargs)


def _make_pipeline(qdrant_entities):
    """Minimal RAGPipeline built via __new__ — bypasses __init__ safely."""
    from vectors.rag import RAGPipeline

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = MagicMock()
    pipeline.config.entity_extraction_concurrency = 4
    pipeline.lm_client = AsyncMock()
    pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.0] * 8)
    pipeline.vector_store = AsyncMock()
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
    pipeline._qdrant_entities = qdrant_entities
    pipeline.schedule_detection = MagicMock()
    return pipeline


def _make_doc():
    doc = MagicMock()
    doc.chunks = [{"chunk_id": 0, "chunk_text": "text"}]
    return doc


async def _drive(pipeline, entities, file_path, root_id="root_id"):
    """Run _extract_and_merge with EntityExtractor stubbed to return `entities`."""
    entity_map = MagicMock()
    entity_map.entities = entities

    with patch("vectors.rag.EntityExtractor") as MockExtractor:
        inst = AsyncMock()
        inst.extract_file = AsyncMock(return_value=entity_map)
        MockExtractor.return_value = inst
        with patch("vectors.rag.annotate_chunks"):
            with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
                await pipeline._extract_and_merge(
                    file_path, _make_doc(), root_id, "path_key"
                )


# ---------------------------------------------------------------------------
# Test A — id-consistency
# ---------------------------------------------------------------------------


def test_upsert_entity_id_matches_graph_store_id():
    """The entity_id sent to upsert must equal graph_store._entity_id(...)."""

    async def _run():
        recorder = _RecordingEntities()
        pipeline = _make_pipeline(recorder)
        entity = Entity(name="PositionEngine", type="class", description="d")

        await _drive(pipeline, [entity], Path("/tmp/a.py"), root_id="root_id")

        assert len(recorder.calls) == 1
        assert recorder.calls[0]["entity_id"] == entity_id(
            "PositionEngine", "class", "root_id"
        )
        # payload type_ and the id-computation type must be the same value
        assert recorder.calls[0]["type_"] == "class"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Test B — sibling independence + enriched diagnostics
# ---------------------------------------------------------------------------


def test_one_entity_failure_does_not_cancel_siblings(caplog):
    """A failing entity must not prevent the sibling from being upserted, and the
    failure must be logged once with enriched, stack-traced diagnostics plus a
    count summary; stats.entities_embed_failed must reflect the failure."""

    async def _run():
        recorder = _RecordingEntities(fail_names={"Bad"})
        pipeline = _make_pipeline(recorder)
        bad = Entity(name="Bad", type="function", description="d")
        good = Entity(name="Good", type="function", description="d")

        with caplog.at_level(logging.WARNING, logger="vectors.rag"):
            await _drive(pipeline, [bad, good], Path("/tmp/b.py"), root_id="root_id")

        # Sibling independence: Good was still upserted, Bad was not.
        upserted_names = {c["name"] for c in recorder.calls}
        assert upserted_names == {"Good"}

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        # Exactly one enriched per-entity warning + one count summary.
        per_entity = [r for r in warnings if "upsert failed for" in r.getMessage()]
        summary = [r for r in warnings if "failures for" in r.getMessage()]
        assert len(per_entity) == 1
        assert len(summary) == 1

        # Enriched diagnostics: names the failing entity, its concrete type, its
        # attribute keys, and carries a stack trace (exc_info).
        rec = per_entity[0]
        msg = rec.getMessage()
        assert "Bad" in msg
        assert "Entity" in msg  # type(entity).__name__
        assert "name" in msg    # an attribute key from the entity __dict__
        assert rec.exc_info is not None

        # Count summary reports 1 of 2 failed.
        assert "1/2" in summary[0].getMessage()

        stats = pipeline._graph_stats["root_id"]
        assert stats.entities_embed_failed == 1
        assert stats.entities_found == 2

    asyncio.run(_run())
