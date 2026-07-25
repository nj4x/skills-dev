"""Tests for QdrantCommunities — Phase 2B GraphRAG community collection."""

from __future__ import annotations

import asyncio

import pytest

from vectors.qdrant import (
    QdrantCommunities,
    CommunityCollectionConfigError,
    CollectionMissingError,
    COMMUNITIES_COLLECTION,
    _make_community_point_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DIM = 4  # tiny dimension for speed


def _vec(*values: float) -> list[float]:
    """Return a padded vector of length DIM."""
    v = list(values)
    while len(v) < DIM:
        v.append(0.0)
    return v[:DIM]


def _report(community_id: str, summary: str = "test", level: int = 0) -> dict:
    return {
        "community_id": community_id,
        "summary": summary,
        "level": level,
        "vector": _vec(0.1, 0.2, 0.3, 0.4),
    }


# ---------------------------------------------------------------------------
# 1. test_ensure_collection_creates_new
# ---------------------------------------------------------------------------


def test_ensure_collection_creates_new():
    """initialize() must create the collection with correct vector size."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        info = await vc._client.get_collection(vc.collection_name)
        actual_size = info.config.params.vectors.size
        assert actual_size == DIM, f"Expected dim={DIM}, got {actual_size}"
        assert vc.collection_name == COMMUNITIES_COLLECTION

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 2. test_ensure_collection_no_recreate_on_mismatch
# ---------------------------------------------------------------------------


def test_ensure_collection_no_recreate_on_mismatch():
    """Re-calling ensure_collection with a different dim must raise CommunityCollectionConfigError."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)  # creates with DIM=4

        # Simulate a caller who now thinks the dimension is different.
        vc.vector_size = DIM + 4  # 8

        with pytest.raises(CommunityCollectionConfigError) as exc_info:
            await vc.ensure_collection()

        msg = str(exc_info.value)
        assert "mismatch" in msg.lower()
        # Collection must still exist (not deleted).
        info = await vc._client.get_collection(vc.collection_name)
        assert info.config.params.vectors.size == DIM

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 3. test_upsert_and_search_by_committed_version
# ---------------------------------------------------------------------------


def test_upsert_and_search_by_committed_version():
    """Search only returns results matching the committed (version, build_id) pair."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        reports = [_report(f"c{i}") for i in range(3)]
        await vc.upsert_generation("root1", graph_version=1, build_id="b1", community_reports=reports)

        # Also upsert an unrelated generation.
        await vc.upsert_generation("root1", graph_version=2, build_id="b1", community_reports=[_report("cx")])

        # Search committed generation.
        results_v1 = await vc.search("root1", _vec(0.1, 0.2, 0.3, 0.4), committed_version=1, committed_build_id="b1", limit=10)
        assert len(results_v1) == 3, f"Expected 3 results, got {len(results_v1)}"

        # Wrong version.
        results_v99 = await vc.search("root1", _vec(0.1, 0.2, 0.3, 0.4), committed_version=99, committed_build_id="b1", limit=10)
        assert len(results_v99) == 0

        # Wrong build_id.
        results_bx = await vc.search("root1", _vec(0.1, 0.2, 0.3, 0.4), committed_version=1, committed_build_id="b2", limit=10)
        assert len(results_bx) == 0

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 4. test_list_by_root_with_level_filter
# ---------------------------------------------------------------------------


def test_list_by_root_with_level_filter():
    """list_by_root must filter by level when requested."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        reports = [
            _report("c0", level=0),
            _report("c1", level=0),
            _report("c2", level=1),
        ]
        await vc.upsert_generation("root1", graph_version=1, build_id="b1", community_reports=reports)

        level0 = await vc.list_by_root("root1", 1, "b1", level=0)
        assert len(level0) == 2
        assert all(r["level"] == 0 for r in level0)

        all_levels = await vc.list_by_root("root1", 1, "b1", level=None)
        assert len(all_levels) == 3

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 5. test_get_by_id_returns_correct_community
# ---------------------------------------------------------------------------


def test_get_by_id_returns_correct_community():
    """get_by_id must retrieve the correct payload for a specific community_id."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        reports = [_report("alpha"), _report("beta"), _report("gamma")]
        await vc.upsert_generation("root1", graph_version=1, build_id="b1", community_reports=reports)

        result = await vc.get_by_id("root1", "beta", committed_version=1, committed_build_id="b1")
        assert result is not None
        assert result["community_id"] == "beta"

        missing = await vc.get_by_id("root1", "nonexistent", committed_version=1, committed_build_id="b1")
        assert missing is None

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 6. test_delete_generation_removes_only_that_build
# ---------------------------------------------------------------------------


def test_delete_generation_removes_only_that_build():
    """delete_generation must remove the target build without touching other builds."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        reports_b1 = [_report("c0"), _report("c1")]
        reports_b2 = [_report("c2"), _report("c3")]

        await vc.upsert_generation("root1", graph_version=1, build_id="b1", community_reports=reports_b1)
        await vc.upsert_generation("root1", graph_version=1, build_id="b2", community_reports=reports_b2)

        await vc.delete_generation("root1", graph_version=1, build_id="b1")

        after_b1 = await vc.list_by_root("root1", committed_version=1, committed_build_id="b1")
        assert len(after_b1) == 0, f"Expected 0 after delete, got {len(after_b1)}"

        after_b2 = await vc.list_by_root("root1", committed_version=1, committed_build_id="b2")
        assert len(after_b2) == 2

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. test_delete_all_except_keeps_committed
# ---------------------------------------------------------------------------


def test_delete_all_except_keeps_committed():
    """delete_all_except must keep only the nominated generation."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        # Three generations for the same root.
        await vc.upsert_generation("root1", 1, "draft", [_report("c0"), _report("c1")])
        await vc.upsert_generation("root1", 2, "candidate", [_report("c2")])
        await vc.upsert_generation("root1", 2, "final", [_report("c3"), _report("c4")])

        await vc.delete_all_except("root1", keep_version=2, keep_build_id="final")

        kept = await vc.list_by_root("root1", committed_version=2, committed_build_id="final", limit=100)
        assert len(kept) == 2

        gone_draft = await vc.list_by_root("root1", committed_version=1, committed_build_id="draft", limit=100)
        assert len(gone_draft) == 0

        gone_candidate = await vc.list_by_root("root1", committed_version=2, committed_build_id="candidate", limit=100)
        assert len(gone_candidate) == 0

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 8. test_candidate_cleanup_on_gate_failure
# ---------------------------------------------------------------------------


def test_candidate_cleanup_on_gate_failure():
    """Simulates gate failure: upsert candidate, then delete it; nothing found for that build."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        candidate_reports = [_report("cx"), _report("cy")]
        await vc.upsert_generation("root1", graph_version=3, build_id="gate-fail", community_reports=candidate_reports)

        # Gate fails — clean up candidate.
        await vc.delete_generation("root1", graph_version=3, build_id="gate-fail")

        results = await vc.list_by_root("root1", committed_version=3, committed_build_id="gate-fail", limit=100)
        assert len(results) == 0

        await vc.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 9. test_close_idempotent
# ---------------------------------------------------------------------------


def test_close_idempotent():
    """Calling close() twice must not raise."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)
        await vc.close()
        await vc.close()  # second close — must be a no-op

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# 10. test_collection_missing_error_on_search
# ---------------------------------------------------------------------------


def test_collection_missing_error_on_search():
    """After the collection is manually deleted, search must raise CollectionMissingError."""

    async def _run():
        vc = QdrantCommunities(url=None)
        await vc.initialize(embedding_dimension=DIM)

        # Manually delete the underlying Qdrant collection.
        await vc._client.delete_collection(vc.collection_name)

        with pytest.raises(CollectionMissingError) as exc_info:
            await vc.search("root1", _vec(0.1, 0.2, 0.3, 0.4), committed_version=1, committed_build_id="b1")

        assert exc_info.value.root_id == "root1"

        # Don't call close() — client still open but collection gone; no double-error.
        await vc._client.close()
        vc._client = None

    asyncio.run(_run())
