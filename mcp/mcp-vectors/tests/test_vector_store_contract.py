"""Contract test suite for VectorStoreProtocol adapters.

Runs identical assertions against QdrantVectorStore (in-memory mode)
and InMemoryVectorStore so that behavioural drift is caught before it
reaches production.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from vectors.qdrant import QdrantVectorStore
from vectors.testing import InMemoryVectorStore


ADAPTERS = [
    pytest.param(lambda: QdrantVectorStore(), id="qdrant-in-memory"),
    pytest.param(lambda: InMemoryVectorStore(vector_size=4), id="in-memory"),
]


def _vec(*values: float) -> list[float]:
    """Pad/truncate to exactly 4 floats for tests."""
    base = list(values) + [0.0] * 4
    return base[:4]


def _make_chunks(n: int, start: int = 0) -> tuple[list[dict], list[list[float]]]:
    chunks = []
    vectors = []
    for i in range(n):
        cid = start + i
        chunks.append({
            "chunk_id": cid,
            "text": f"chunk content {cid}",
            "start_char": cid * 100,
            "end_char": cid * 100 + 50,
        })
        v = _vec(float(cid) * 0.1, 0.5, 0.3, 0.1)
        vectors.append(v)
    return chunks, vectors


@pytest.fixture(params=ADAPTERS)
def store(request) -> Any:
    factory = request.param
    s = factory()
    s.update_vector_size(4)
    asyncio.run(s.initialize())
    yield s
    asyncio.run(s.close())


# ---------------------------------------------------------------------------
# Upsert + list
# ---------------------------------------------------------------------------


def test_upsert_chunks_returns_count(store):
    chunks, vecs = _make_chunks(3)
    n = asyncio.run(store.upsert_chunks(
        file_path="/proj/foo.py",
        file_name="foo.py",
        chunks=chunks,
        embeddings=vecs,
        root_path="/proj",
    ))
    assert n == 3


def test_list_indexed_files_after_upsert(store):
    chunks, vecs = _make_chunks(2)
    asyncio.run(store.upsert_chunks("/proj/foo.py", "foo.py", chunks, vecs, root_path="/proj"))
    result = asyncio.run(store.list_indexed_files())
    files = result["files"]
    assert result["total_unique_files_scanned"] == 1
    assert len(files) == 1
    assert files[0]["chunk_count"] == 2


def test_list_indexed_files_multiple_files(store):
    for i in range(3):
        chunks, vecs = _make_chunks(1)
        asyncio.run(store.upsert_chunks(f"/proj/f{i}.py", f"f{i}.py", chunks, vecs))
    result = asyncio.run(store.list_indexed_files())
    assert result["total_unique_files_scanned"] == 3


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_document_by_path_key_removes_from_listing(store):
    chunks, vecs = _make_chunks(2)
    asyncio.run(store.upsert_chunks("/proj/bar.py", "bar.py", chunks, vecs))
    deleted = asyncio.run(store.delete_document_by_path_key("/proj/bar.py"))
    assert deleted > 0
    result = asyncio.run(store.list_indexed_files())
    assert result["total_unique_files_scanned"] == 0


def test_delete_document_chunks_from(store):
    chunks, vecs = _make_chunks(5)
    asyncio.run(store.upsert_chunks("/proj/baz.py", "baz.py", chunks, vecs))
    deleted = asyncio.run(store.delete_document_chunks_from("/proj/baz.py", min_chunk_id=3))
    assert deleted == 2
    result = asyncio.run(store.list_indexed_files())
    assert result["files"][0]["chunk_count"] == 3


# ---------------------------------------------------------------------------
# Search shape
# ---------------------------------------------------------------------------


def test_search_returns_search_result_shape(store):
    from vectors.qdrant import SearchResult
    chunks, vecs = _make_chunks(3)
    asyncio.run(store.upsert_chunks("/proj/search.py", "search.py", chunks, vecs))
    results = asyncio.run(store.search(query_vector=_vec(0.1, 0.5, 0.3, 0.1), limit=5))
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, SearchResult)
        assert hasattr(r, "id")
        assert hasattr(r, "score")
        assert hasattr(r, "file_path")
        assert hasattr(r, "chunk_text")


def test_search_respects_limit(store):
    chunks, vecs = _make_chunks(10)
    asyncio.run(store.upsert_chunks("/proj/many.py", "many.py", chunks, vecs))
    results = asyncio.run(store.search(query_vector=_vec(0.5, 0.5, 0.0, 0.0), limit=3))
    assert len(results) <= 3


def test_search_returns_empty_when_nothing_indexed(store):
    results = asyncio.run(store.search(query_vector=_vec(1.0, 0.0, 0.0, 0.0)))
    assert results == []


# ---------------------------------------------------------------------------
# is_path_indexed
# ---------------------------------------------------------------------------


def test_is_path_indexed_true_after_upsert(store):
    chunks, vecs = _make_chunks(1)
    asyncio.run(store.upsert_chunks("/proj/check.py", "check.py", chunks, vecs))
    assert asyncio.run(store.is_path_indexed("/proj/check.py"))


def test_is_path_indexed_false_for_missing(store):
    assert not asyncio.run(store.is_path_indexed("/proj/ghost.py"))


# ---------------------------------------------------------------------------
# Scroll bounded
# ---------------------------------------------------------------------------


def test_scroll_points_bounded_returns_points(store):
    chunks, vecs = _make_chunks(3)
    asyncio.run(store.upsert_chunks("/proj/sc.py", "sc.py", chunks, vecs))
    result = asyncio.run(store.scroll_points_bounded())
    assert "points" in result
    assert "scanned_points" in result
    assert "partial" in result
    assert result["scanned_points"] == 3


# ---------------------------------------------------------------------------
# chunk_text round-trip value (Q2a — drift guard)
# ---------------------------------------------------------------------------


def test_search_chunk_text_round_trips(store):
    """chunk_text value must survive upsert → search unchanged across adapters."""
    chunks = [{"chunk_id": 0, "text": "hello world", "start_char": 0, "end_char": 11}]
    vecs = [_vec(1.0, 0.0, 0.0, 0.0)]
    asyncio.run(store.upsert_chunks("/proj/ct.py", "ct.py", chunks, vecs))
    results = asyncio.run(store.search(query_vector=_vec(1.0, 0.0, 0.0, 0.0), limit=1))
    assert len(results) == 1
    assert results[0].chunk_text == "hello world", (
        f"chunk_text round-trip failed: got {results[0].chunk_text!r}"
    )


# ---------------------------------------------------------------------------
# update_chunk_entities (Q2b — missing contract coverage)
# ---------------------------------------------------------------------------


def test_update_chunk_entities_persists_entity_names(store):
    """update_chunk_entities must update entity_names in the store."""
    chunks, vecs = _make_chunks(2)
    asyncio.run(store.upsert_chunks("/proj/ent.py", "ent.py", chunks, vecs))
    updated = [
        {"chunk_id": 0, "entity_names": ["Foo", "Bar"]},
        {"chunk_id": 1, "entity_names": ["Baz"]},
    ]
    asyncio.run(store.update_chunk_entities("/proj/ent.py", updated))
    # Re-fetch via search and check entity_names appear in metadata
    results = asyncio.run(store.search(query_vector=_vec(0.0, 0.5, 0.3, 0.1), limit=5))
    names_by_chunk = {r.chunk_id: r.metadata.get("entity_names", []) for r in results}
    assert "Foo" in names_by_chunk.get(0, []), f"Chunk 0 entity_names not updated: {names_by_chunk}"
    assert "Baz" in names_by_chunk.get(1, []), f"Chunk 1 entity_names not updated: {names_by_chunk}"
