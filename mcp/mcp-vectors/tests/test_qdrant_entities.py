"""Tests for QdrantEntities — entity embedding store (ADR-0009–0021, Seam 2)."""

from __future__ import annotations

import asyncio

from vectors.qdrant import QdrantEntities, ENTITIES_COLLECTION


DIM = 4


def _vec(*values: float) -> list[float]:
    v = list(values)
    while len(v) < DIM:
        v.append(0.0)
    return v[:DIM]


# ---------------------------------------------------------------------------
# 1. Collection creation
# ---------------------------------------------------------------------------


def test_ensure_collection_creates_new():
    """initialize() creates the entities collection with correct vector size."""

    async def _run():
        qe = QdrantEntities(url=None)
        await qe.initialize(embedding_dimension=DIM)

        info = await qe._client.get_collection(qe.collection_name)
        actual_size = info.config.params.vectors.size
        assert actual_size == DIM
        assert qe.collection_name == ENTITIES_COLLECTION

        await qe.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. Upsert and search
# ---------------------------------------------------------------------------


def test_upsert_and_search_returns_entity():
    """upsert() stores an entity; search() returns it for a matching query."""

    async def _run():
        qe = QdrantEntities(url=None)
        await qe.initialize(embedding_dimension=DIM)

        await qe.upsert(
            entity_id="ent-1",
            root_id="root-a",
            name="MyClass",
            type_="class",
            embedding=_vec(1.0, 0.0, 0.0, 0.0),
        )

        results = await qe.search(
            root_id="root-a",
            query_embedding=_vec(1.0, 0.0, 0.0, 0.0),
            limit=5,
        )
        assert len(results) == 1
        assert results[0]["entity_id"] == "ent-1"
        assert results[0]["name"] == "MyClass"
        assert results[0]["type"] == "class"
        assert "score" in results[0]

        await qe.close()

    asyncio.run(_run())


def test_search_is_root_scoped():
    """search() only returns entities for the queried root_id."""

    async def _run():
        qe = QdrantEntities(url=None)
        await qe.initialize(embedding_dimension=DIM)

        await qe.upsert("ent-a", "root-A", "EntityA", "func", _vec(1.0, 0.0, 0.0, 0.0))
        await qe.upsert("ent-b", "root-B", "EntityB", "func", _vec(1.0, 0.0, 0.0, 0.0))

        results = await qe.search("root-A", _vec(1.0, 0.0, 0.0, 0.0), limit=10)
        ids = [r["entity_id"] for r in results]
        assert "ent-a" in ids
        assert "ent-b" not in ids

        await qe.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. delete_by_root_id
# ---------------------------------------------------------------------------


def test_delete_by_root_id_removes_all_entities_for_root():
    """delete_by_root_id removes all entities for the given root."""

    async def _run():
        qe = QdrantEntities(url=None)
        await qe.initialize(embedding_dimension=DIM)

        await qe.upsert("ent-1", "root-X", "E1", "func", _vec(0.5, 0.5, 0.0, 0.0))
        await qe.upsert("ent-2", "root-X", "E2", "func", _vec(0.5, 0.5, 0.0, 0.0))
        await qe.upsert("ent-3", "root-Y", "E3", "func", _vec(0.5, 0.5, 0.0, 0.0))

        await qe.delete_by_root_id("root-X")

        results_x = await qe.search("root-X", _vec(0.5, 0.5, 0.0, 0.0), limit=10)
        assert results_x == []

        results_y = await qe.search("root-Y", _vec(0.5, 0.5, 0.0, 0.0), limit=10)
        assert len(results_y) == 1
        assert results_y[0]["entity_id"] == "ent-3"

        await qe.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. delete_by_entity_ids
# ---------------------------------------------------------------------------


def test_delete_by_entity_ids_removes_specified_entities():
    """delete_by_entity_ids removes only the given entity IDs for that root."""

    async def _run():
        qe = QdrantEntities(url=None)
        await qe.initialize(embedding_dimension=DIM)

        await qe.upsert("keep-1", "root-Z", "Keep1", "func", _vec(0.1, 0.0, 0.0, 0.0))
        await qe.upsert("del-1",  "root-Z", "Del1",  "func", _vec(0.1, 0.0, 0.0, 0.0))
        await qe.upsert("del-2",  "root-Z", "Del2",  "func", _vec(0.1, 0.0, 0.0, 0.0))

        await qe.delete_by_entity_ids("root-Z", ["del-1", "del-2"])

        results = await qe.search("root-Z", _vec(0.1, 0.0, 0.0, 0.0), limit=10)
        ids = [r["entity_id"] for r in results]
        assert "keep-1" in ids
        assert "del-1" not in ids
        assert "del-2" not in ids

        await qe.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. Idempotent upsert (point ID stability)
# ---------------------------------------------------------------------------


def test_upsert_is_idempotent():
    """Re-upserting the same entity_id/root_id updates without creating a duplicate."""

    async def _run():
        qe = QdrantEntities(url=None)
        await qe.initialize(embedding_dimension=DIM)

        await qe.upsert("ent-u", "root-R", "OrigName", "func", _vec(1.0, 0.0, 0.0, 0.0))
        await qe.upsert("ent-u", "root-R", "UpdatedName", "func", _vec(0.0, 1.0, 0.0, 0.0))

        results = await qe.search("root-R", _vec(0.0, 1.0, 0.0, 0.0), limit=10)
        assert len(results) == 1
        assert results[0]["name"] == "UpdatedName"

        await qe.close()

    asyncio.run(_run())
