"""Contract test suite for CommunityVectorStoreProtocol adapters.

Runs identical assertions against QdrantCommunities (in-memory mode)
and InMemoryCommunities so that behavioural drift is caught before
it reaches production.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from vectors.qdrant import QdrantCommunities
from vectors.testing import InMemoryCommunities

DIM = 4
ADAPTERS = [
    pytest.param(lambda: QdrantCommunities(url=None), id="qdrant-in-memory"),
    pytest.param(lambda: InMemoryCommunities(), id="in-memory"),
]


def _vec(*values: float) -> list[float]:
    base = list(values) + [0.0] * DIM
    return base[:DIM]


def _make_reports(n: int, level: int = 0) -> list[dict]:
    return [
        {
            "community_id": f"c{i}",
            "level": level,
            "title": f"Community {i}",
            "summary": f"Summary for community {i}",
            "vector": _vec(float(i) * 0.1, 0.5, 0.3, 0.1),
        }
        for i in range(n)
    ]


@pytest.fixture(params=ADAPTERS)
def store(request) -> Any:
    factory = request.param
    s = factory()
    asyncio.run(s.initialize(embedding_dimension=DIM))
    yield s
    asyncio.run(s.close())


# ---------------------------------------------------------------------------
# Upsert + list
# ---------------------------------------------------------------------------


def test_upsert_and_list_by_root(store):
    reports = _make_reports(3)
    asyncio.run(store.upsert_generation("root1", graph_version=1, build_id="b1", community_reports=reports))
    result = asyncio.run(store.list_by_root("root1", committed_version=1, committed_build_id="b1"))
    assert len(result) == 3
    ids = [r["community_id"] for r in result]
    assert "c0" in ids and "c1" in ids and "c2" in ids


def test_list_by_root_wrong_version_returns_empty(store):
    reports = _make_reports(2)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    result = asyncio.run(store.list_by_root("root1", committed_version=99, committed_build_id="b1"))
    assert result == []


def test_list_by_root_level_filter(store):
    reports_l0 = _make_reports(2, level=0)
    reports_l1 = _make_reports(2, level=1)
    all_reports = reports_l0 + [dict(r, community_id=f"l1_{r['community_id']}") for r in reports_l1]
    asyncio.run(store.upsert_generation("root1", 1, "b1", all_reports))
    result = asyncio.run(store.list_by_root("root1", 1, "b1", level=0))
    assert all(r["level"] == 0 for r in result)


def test_list_by_root_sorted_by_level_then_id(store):
    reports = _make_reports(3, level=0)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    result = asyncio.run(store.list_by_root("root1", 1, "b1"))
    ids = [r["community_id"] for r in result]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


def test_get_by_id_returns_report(store):
    reports = _make_reports(3)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    result = asyncio.run(store.get_by_id("root1", "c1", 1, "b1"))
    assert result is not None
    assert result["community_id"] == "c1"
    assert result["title"] == "Community 1"


def test_get_by_id_missing_returns_none(store):
    reports = _make_reports(2)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    result = asyncio.run(store.get_by_id("root1", "nonexistent", 1, "b1"))
    assert result is None


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_generation_removes_reports(store):
    reports = _make_reports(3)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    asyncio.run(store.delete_generation("root1", 1, "b1"))
    result = asyncio.run(store.list_by_root("root1", 1, "b1"))
    assert result == []


def test_delete_all_except_keeps_committed(store):
    for v in range(1, 4):
        asyncio.run(store.upsert_generation("root1", v, f"b{v}", _make_reports(2)))
    asyncio.run(store.delete_all_except("root1", keep_version=2, keep_build_id="b2"))
    assert asyncio.run(store.list_by_root("root1", 2, "b2")) != []
    assert asyncio.run(store.list_by_root("root1", 1, "b1")) == []
    assert asyncio.run(store.list_by_root("root1", 3, "b3")) == []


def test_delete_all_except_does_not_affect_other_roots(store):
    asyncio.run(store.upsert_generation("root1", 1, "b1", _make_reports(2)))
    asyncio.run(store.upsert_generation("root2", 1, "b1", _make_reports(2)))
    asyncio.run(store.delete_all_except("root1", keep_version=1, keep_build_id="b1"))
    assert asyncio.run(store.list_by_root("root2", 1, "b1")) != []


# ---------------------------------------------------------------------------
# Search shape
# ---------------------------------------------------------------------------


def test_search_returns_payloads_with_score(store):
    reports = _make_reports(3)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    results = asyncio.run(store.search("root1", _vec(0.1, 0.5, 0.3, 0.1), 1, "b1", limit=5))
    assert isinstance(results, list)
    for r in results:
        assert "community_id" in r
        assert "score" in r
        assert "vector" not in r


def test_search_respects_limit(store):
    reports = _make_reports(10)
    asyncio.run(store.upsert_generation("root1", 1, "b1", reports))
    results = asyncio.run(store.search("root1", _vec(0.5, 0.5, 0.0, 0.0), 1, "b1", limit=3))
    assert len(results) <= 3


def test_search_empty_when_no_reports(store):
    results = asyncio.run(store.search("root_x", _vec(1.0, 0.0, 0.0, 0.0), 1, "b1"))
    assert results == []
