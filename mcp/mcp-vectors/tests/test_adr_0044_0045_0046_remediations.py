"""Tests for ADR-0044/0045/0046 remediations.

Seam 1: re-index preserves entity vectors (no delete-after-upsert).
Seam 2: reconciliation calls delete_by_root_id for PURGED and REMAPPED roots.
Seam 3: get_graph_stats() serializes entity_embedding_enabled/entities_embedded/entities_total.
Seam 4: zero-entity/non-empty-stub file embeds stubs.
Seam 5: extract_entities_from_file() wires entity and stub embedding.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from vectors.entity_extractor import Entity
from vectors.graph_store import entity_id


# ---------------------------------------------------------------------------
# Shared test infrastructure
# ---------------------------------------------------------------------------


class FakeQdrantEntities:
    """Spy for QdrantEntities: records upsert/delete calls, never fails."""

    def __init__(self):
        self.upserted: list[dict] = []
        self.deleted_root_ids: list[str] = []
        self.deleted_entity_ids: list[tuple[str, list[str]]] = []

    async def upsert(self, **kwargs) -> None:
        self.upserted.append(kwargs)

    async def delete_by_root_id(self, root_id: str) -> None:
        self.deleted_root_ids.append(root_id)

    async def delete_by_entity_ids(self, root_id: str, ids: list[str]) -> None:
        self.deleted_entity_ids.append((root_id, ids))


def _make_pipeline(qdrant_entities=None):
    from vectors.rag import RAGPipeline

    pipeline = RAGPipeline.__new__(RAGPipeline)
    pipeline.config = MagicMock()
    pipeline.config.entity_extraction_concurrency = 4
    pipeline.config.llm_provider = "stub"
    pipeline.lm_client = AsyncMock()
    pipeline.lm_client.get_embedding = AsyncMock(return_value=[0.1] * 4)
    pipeline.vector_store = AsyncMock()
    pipeline._initialized = True
    pipeline._extraction_cache = MagicMock()
    pipeline._graph_store = MagicMock()
    pipeline.parser = MagicMock()
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


async def _drive_extract_and_merge(pipeline, entities, stubs=None, root_id="root_id"):
    """Run _extract_and_merge with EntityExtractor and graph_store stubbed."""
    entity_map = MagicMock()
    entity_map.entities = entities

    stubs = stubs or []
    with patch("vectors.rag.EntityExtractor") as MockExtractor:
        inst = AsyncMock()
        inst.extract_file = AsyncMock(return_value=entity_map)
        MockExtractor.return_value = inst
        with patch("vectors.rag.annotate_chunks"):
            with patch("asyncio.to_thread", new=AsyncMock(return_value=(1, stubs, []))):
                await pipeline._extract_and_merge(
                    Path("/tmp/a.py"), _make_doc(), root_id, "path_key"
                )


# ---------------------------------------------------------------------------
# Seam 1: re-index preserves entity vectors (no delete-after-upsert)
# ---------------------------------------------------------------------------


def test_reindex_preserves_entity_vectors_no_delete():
    """Re-indexed entities' Qdrant vectors must persist after _extract_and_merge.

    ADR-0044 fix: the delete_by_entity_ids call is removed from _extract_and_merge,
    so entity vectors survive re-index operations.
    """
    async def _run():
        spy = FakeQdrantEntities()
        pipeline = _make_pipeline(qdrant_entities=spy)

        entity = Entity(name="MyClass", type="class", description="d")
        stub = {"id": entity_id("Dep", "class", "root_id"), "name": "Dep", "type": "class"}

        await _drive_extract_and_merge(pipeline, [entity], stubs=[stub])

        # Entities and stubs were upserted
        upserted_names = {c["name"] for c in spy.upserted}
        assert "MyClass" in upserted_names, "entity vector must be upserted"
        assert "Dep" in upserted_names, "stub vector must be upserted"

        # No delete_by_entity_ids calls were made
        assert spy.deleted_entity_ids == [], (
            "delete_by_entity_ids must not be called during re-index (ADR-0044 fix)"
        )

        # Stats updated
        stats = pipeline._graph_stats["root_id"]
        assert stats.entities_embedded == 2
        assert stats.entities_total == 2

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Seam 2: reconciliation calls delete_by_root_id for PURGED and REMAPPED roots
# ---------------------------------------------------------------------------


def _make_epoch(**classifications):
    """Build a minimal ReconciliationEpoch for unit testing _apply_vector_phase."""
    from vectors.reconciliation import ReconciliationEpoch
    epoch = ReconciliationEpoch(
        epoch_id="test-epoch",
        schema_version=1,
        owner_lease="test-owner",
        heartbeat_at=0.0,
        lease_expires_at=0.0,
        resolver_fingerprint="",
        config_fingerprint="",
        generation=1,
        status="reconciling",
        classifications=dict(classifications),
        counts={},
    )
    return epoch


def _make_purged(source_root: str):
    from vectors.reconciliation import RootClassification, SERVING_PURGED
    return RootClassification(
        source_root=source_root,
        resolution_status="no_repository",
        destination_root=None,
        serving_state=SERVING_PURGED,
    )


def _make_remapped(source_root: str, dest: str):
    from vectors.reconciliation import RootClassification, SERVING_REMAPPED
    return RootClassification(
        source_root=source_root,
        resolution_status="supported_working_tree",
        destination_root=dest,
        serving_state=SERVING_REMAPPED,
    )


def _make_reconciler(mock_vs, spy_qdrant):
    from vectors.reconciliation import RegistryReconciler
    reconciler = RegistryReconciler.__new__(RegistryReconciler)
    reconciler._vector_store = mock_vs
    reconciler._qdrant_entities = spy_qdrant
    reconciler._graph_store = None
    reconciler._persist = MagicMock()
    return reconciler


def test_reconciliation_deletes_entity_vectors_for_purged_roots():
    """_apply_vector_phase must call delete_by_root_id for PURGED roots.

    ADR-0044 fix: RegistryReconciler gains qdrant_entities parameter and
    cleans up entity vectors when a root is purged.
    """
    async def _run():
        spy = FakeQdrantEntities()
        mock_vs = AsyncMock()
        mock_vs.delete_root = AsyncMock(return_value=5)

        reconciler = _make_reconciler(mock_vs, spy)
        epoch = _make_epoch(purged_root=_make_purged("purged_root"))
        await reconciler._apply_vector_phase(epoch)

        assert spy.deleted_root_ids == ["purged_root"], (
            "delete_by_root_id must be called exactly once for PURGED root"
        )

    asyncio.run(_run())


def test_reconciliation_deletes_entity_vectors_for_remapped_roots():
    """_apply_vector_phase must call delete_by_root_id for REMAPPED roots.

    ADR-0044 M2 fix: entity IDs encode source_root; after remap those vectors
    are unreachable under the destination root, so they must be cleaned up.
    """
    async def _run():
        spy = FakeQdrantEntities()
        mock_vs = AsyncMock()
        mock_vs.remap_root = AsyncMock(return_value=3)

        reconciler = _make_reconciler(mock_vs, spy)
        epoch = _make_epoch(
            remapped_root=_make_remapped("remapped_root", "canonical_root"),
        )

        with patch("vectors.reconciliation.PathPolicy") as mock_pp:
            mock_pp.resolve.return_value = "/canonical_root"
            await reconciler._apply_vector_phase(epoch)

        assert "remapped_root" in spy.deleted_root_ids, (
            "delete_by_root_id must be called for REMAPPED root (M2 fix)"
        )

    asyncio.run(_run())


def test_reconciliation_skips_entity_delete_when_qdrant_entities_none():
    """When qdrant_entities is None (ENTITY_EXTRACTION off), entity deletion is silently skipped."""
    async def _run():
        mock_vs = AsyncMock()
        mock_vs.delete_root = AsyncMock(return_value=5)

        reconciler = _make_reconciler(mock_vs, spy_qdrant=None)

        epoch = _make_epoch(purged_root=_make_purged("purged_root"))
        await reconciler._apply_vector_phase(epoch)

        # delete_root was still called on the vector store
        mock_vs.delete_root.assert_awaited_once_with("purged_root")
        # No AttributeError — qdrant_entities being None is silently handled

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Seam 3: get_graph_stats() serializes entity coverage metrics
# ---------------------------------------------------------------------------


def test_get_graph_stats_includes_entity_coverage_fields():
    """get_graph_stats() must serialize entity_embedding_enabled, entities_embedded, entities_total."""
    pipeline = _make_pipeline(qdrant_entities=FakeQdrantEntities())

    stats = pipeline._get_or_create_stats("my_root")
    stats.entities_embedded = 42
    stats.entities_total = 50
    stats.files_extracted = 1
    stats.extraction_started_at = time.time() - 60

    result = pipeline.get_graph_stats("my_root")

    assert result is not None
    assert result["entity_embedding_enabled"] is True
    assert result["entities_embedded"] == 42
    assert result["entities_total"] == 50


def test_get_graph_stats_entity_embedding_enabled_restart_stable():
    """entity_embedding_enabled must be True whenever _qdrant_entities is configured.

    M4 fix: the flag is derived from configuration in get_graph_stats(), not from
    extraction history, so it is correct after a server restart with zero extractions.
    """
    pipeline = _make_pipeline(qdrant_entities=FakeQdrantEntities())
    pipeline._get_or_create_stats("root_x")
    # No extractions have occurred — stats.entity_embedding_enabled is still False.

    result = pipeline.get_graph_stats("root_x")

    assert result is not None
    # Must be True because _qdrant_entities is configured, regardless of extraction history.
    assert result["entity_embedding_enabled"] is True


def test_get_graph_stats_entity_embedding_enabled_false_when_unconfigured():
    """entity_embedding_enabled is False when _qdrant_entities is None."""
    pipeline = _make_pipeline(qdrant_entities=None)
    pipeline._get_or_create_stats("root_x")

    result = pipeline.get_graph_stats("root_x")

    assert result is not None
    assert result["entity_embedding_enabled"] is False
    assert result["entities_embedded"] == 0
    assert result["entities_total"] == 0


# ---------------------------------------------------------------------------
# Seam 4: zero-entity/non-empty-stub file embeds stubs
# ---------------------------------------------------------------------------


def test_zero_entity_file_with_stubs_embeds_stubs():
    """When a file yields zero entities but non-empty stubs, stubs must be embedded.

    ADR-0045 fix: stub embedding is now gated independently of entity presence.
    """
    async def _run():
        spy = FakeQdrantEntities()
        pipeline = _make_pipeline(qdrant_entities=spy)

        stub = {"id": entity_id("DepNode", "class", "root_id"), "name": "DepNode", "type": "class"}

        # entities=[] but stubs=[stub]
        await _drive_extract_and_merge(pipeline, entities=[], stubs=[stub])

        upserted_names = {c["name"] for c in spy.upserted}
        assert "DepNode" in upserted_names, "stub must be embedded even when no entities exist"

        stats = pipeline._graph_stats["root_id"]
        assert stats.entities_embedded == 1
        assert stats.entities_total == 1
        assert stats.entity_embedding_enabled is True

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Seam 5: extract_entities_from_file() wires entity and stub embedding
# ---------------------------------------------------------------------------


def test_extract_entities_from_file_embeds_entities_and_stubs(tmp_path):
    """extract_entities_from_file() must embed both entities and stubs via _embed_entities_and_stubs.

    ADR-0045 fix: the explicit path now calls the shared helper; previously it
    performed no embedding at all.
    """
    async def _run():
        spy = FakeQdrantEntities()
        pipeline = _make_pipeline(qdrant_entities=spy)

        # Write a real file so path.exists() passes
        src = tmp_path / "mod.py"
        src.write_text("class Foo: pass")

        entity = Entity(name="Foo", type="class", description="a class")
        stub = {"id": entity_id("Bar", "class", str(tmp_path)), "name": "Bar", "type": "class"}

        entity_map = MagicMock()
        entity_map.entities = [entity]
        entity_map.edges = []

        with patch("vectors.rag.EntityExtractor") as MockExtractor:
            inst = AsyncMock()
            inst.extract_file = AsyncMock(return_value=entity_map)
            MockExtractor.return_value = inst
            with patch("vectors.rag.annotate_chunks"):
                with patch("asyncio.to_thread", new=AsyncMock(return_value=(1, [stub], []))):
                    with patch("vectors.rag.ENTITY_EXTRACTION", True):
                        result = await pipeline.extract_entities_from_file(
                            src, graph_root_path=tmp_path
                        )

        assert result["success"] is True, f"extract_entities_from_file failed: {result}"

        upserted_names = {c["name"] for c in spy.upserted}
        assert "Foo" in upserted_names, "entity must be embedded via extract_entities_from_file"
        assert "Bar" in upserted_names, "stub must be embedded via extract_entities_from_file"

        # Stats attributed to the correct root
        stats_keys = list(pipeline._graph_stats.keys())
        assert len(stats_keys) == 1
        stats = list(pipeline._graph_stats.values())[0]
        assert stats.entities_embedded == 2
        assert stats.entities_total == 2

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Finding 5: _closing guard prevents embedding during shutdown
# ---------------------------------------------------------------------------


def test_embed_entities_and_stubs_noop_when_closing():
    """When _closing is True, _embed_entities_and_stubs must no-op immediately.

    Finding 5 fix: prevents a race where shutdown sets _closing=True but an
    already-dispatched extract_entities_from_file call still tries to embed.
    """
    async def _run():
        spy = FakeQdrantEntities()
        pipeline = _make_pipeline(qdrant_entities=spy)
        pipeline._closing = True

        entity = Entity(name="Foo", type="class", description="d")
        stub = {"id": entity_id("Bar", "class", "root_id"), "name": "Bar", "type": "class"}
        stats = pipeline._get_or_create_stats("root_id")

        await pipeline._embed_entities_and_stubs([entity], [stub], "root_id", "f.py", stats)

        assert spy.upserted == [], "no upserts must occur when _closing=True"
        assert stats.entities_embedded == 0

    asyncio.run(_run())
