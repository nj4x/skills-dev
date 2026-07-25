"""Tests for QdrantVectorStore Phase 1-D additions: get_points_by_ids and v3 indexes."""

import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock

from vectors.qdrant import QdrantVectorStore


def test_get_points_by_ids_method_exists():
    """The method must be present on the class."""
    assert hasattr(QdrantVectorStore, "get_points_by_ids")
    assert callable(getattr(QdrantVectorStore, "get_points_by_ids"))


def test_get_points_by_ids_empty_list_returns_immediately():
    """Empty input must return [] without touching Qdrant at all."""
    store = QdrantVectorStore()
    # No client is set up; any Qdrant call would raise.
    result = asyncio.run(store.get_points_by_ids([]))
    assert result == []


def test_get_points_by_ids_calls_retrieve():
    """Non-empty list should call client.retrieve with the supplied IDs."""
    async def _run():
        store = QdrantVectorStore(url="http://localhost:6333")
        store._initialized = True

        fake_point = MagicMock()
        fake_point.id = "deadbeef-dead-beef-dead-beefdeadbeef"
        fake_point.payload = {"file_path": "/tmp/foo.py", "chunk_text": "hello"}

        mock_client = AsyncMock()
        mock_client.retrieve = AsyncMock(return_value=[fake_point])
        store._client = mock_client

        ids = ["deadbeef-dead-beef-dead-beefdeadbeef"]
        results = await store.get_points_by_ids(ids)

        mock_client.retrieve.assert_awaited_once_with(
            collection_name=store.collection_name,
            ids=ids,
            with_payload=True,
            with_vectors=False,
        )
        assert len(results) == 1
        assert results[0]["score"] == 1.0
        assert results[0]["payload"]["file_path"] == "/tmp/foo.py"

    asyncio.run(_run())


def test_ensure_payload_indexes_references_entity_names():
    """_ensure_payload_indexes must include the three new v3 fields."""
    src = inspect.getsource(QdrantVectorStore._ensure_payload_indexes)
    assert "entity_names" in src
    assert "parent_symbol" in src
    assert "symbol_type" in src


def test_update_chunk_entities_method_exists():
    """update_chunk_entities must be present on QdrantVectorStore."""
    assert hasattr(QdrantVectorStore, "update_chunk_entities")
    assert callable(getattr(QdrantVectorStore, "update_chunk_entities"))


def test_update_chunk_entities_empty_chunks_returns_immediately():
    """Empty chunk list must return without touching Qdrant."""
    store = QdrantVectorStore()
    # No client initialised; any Qdrant call would raise.
    asyncio.run(store.update_chunk_entities("/tmp/test.py", []))


def test_update_chunk_entities_calls_set_payload():
    """Each chunk must trigger a set_payload call with the correct point_id and payload."""

    async def _run():
        store = QdrantVectorStore(url="http://localhost:6333")
        store._initialized = True

        mock_client = AsyncMock()
        mock_client.set_payload = AsyncMock(return_value=None)
        store._client = mock_client

        chunks = [
            {"chunk_id": 0, "entity_names": ["Alice", "Bob"]},
            {"chunk_id": 1, "entity_names": []},
            {"chunk_id": 2},  # no entity_names key — should default to []
        ]
        file_path = "/tmp/test.py"
        await store.update_chunk_entities(file_path, chunks)

        assert mock_client.set_payload.await_count == 3

        from vectors.qdrant import make_chunk_point_id
        from vectors.paths import PathPolicy

        canonical = PathPolicy.path_key(file_path)
        calls = mock_client.set_payload.await_args_list

        # chunk 0
        call_kwargs = calls[0].kwargs if calls[0].kwargs else calls[0][1]
        assert call_kwargs["payload"] == {"entity_names": ["Alice", "Bob"]}
        assert call_kwargs["points"] == [make_chunk_point_id(canonical, 0)]

        # chunk 2 — missing entity_names defaults to []
        call_kwargs2 = calls[2].kwargs if calls[2].kwargs else calls[2][1]
        assert call_kwargs2["payload"] == {"entity_names": []}

    asyncio.run(_run())
