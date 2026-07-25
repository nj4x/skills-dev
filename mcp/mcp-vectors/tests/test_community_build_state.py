"""Focused regressions for durable SQLite community rebuild state."""

from __future__ import annotations

from vectors.graph_store import GraphStore


ROOT = "durable-community-build-root"


def _dirty_generation(store: GraphStore) -> int:
    return store.mark_communities_dirty(ROOT)


def test_admission_requires_current_dirty_generation_and_single_claim(tmp_path):
    store = GraphStore(str(tmp_path))
    version = _dirty_generation(store)

    assert store.claim_community_build(ROOT, version, "worker-a", 60, now=100) is True
    assert store.claim_community_build(ROOT, version, "worker-b", 60, now=101) is False
    assert store.claim_community_build(ROOT, version + 1, "wrong-version", 60, now=101) is False

    assert store.complete_community_build(ROOT, version, "worker-a") is True
    assert store.replace_communities_if_current(ROOT, version, "published", []) is True
    assert store.claim_community_build(ROOT, version, "clean-generation", 60, now=102) is False


def test_failure_count_parks_exactly_at_five_and_warns_once(tmp_path):
    store = GraphStore(str(tmp_path))
    version = _dirty_generation(store)

    for attempt in range(1, 5):
        token = f"worker-{attempt}"
        assert store.claim_community_build(ROOT, version, token, 60, now=attempt) is True
        assert store.fail_community_build(ROOT, version, token) == (True, False)
        state = store.get_community_build_state(ROOT, version)
        assert state is not None
        assert state.attempts == attempt
        assert state.parked is False
        assert state.warning_emitted is False

    assert store.claim_community_build(ROOT, version, "worker-5", 60, now=5) is True
    assert store.fail_community_build(ROOT, version, "worker-5") == (True, True)

    state = store.get_community_build_state(ROOT, version)
    assert state is not None
    assert state.attempts == 5
    assert state.parked is True
    assert state.warning_emitted is True
    assert state.active_build_token is None
    assert store.claim_community_build(ROOT, version, "worker-6", 60, now=6) is False
    assert store.fail_community_build(ROOT, version, "worker-5") == (False, False)


def test_build_state_is_durable_and_requires_matching_token_and_version(tmp_path):
    store = GraphStore(str(tmp_path))
    version = _dirty_generation(store)
    assert store.claim_community_build(ROOT, version, "owner", 60, now=100) is True

    reopened = GraphStore(str(tmp_path))
    state = reopened.get_community_build_state(ROOT, version)
    assert state is not None
    assert state.active_build_token == "owner"
    assert reopened.complete_community_build(ROOT, version, "not-owner") is False
    assert reopened.fail_community_build(ROOT, version + 1, "owner") == (False, False)

    state = reopened.get_community_build_state(ROOT, version)
    assert state is not None
    assert state.attempts == 0
    assert state.active_build_token == "owner"


def test_expired_lease_is_safely_reclaimed_by_new_claimant(tmp_path):
    store = GraphStore(str(tmp_path))
    version = _dirty_generation(store)
    assert store.claim_community_build(ROOT, version, "crashed-worker", 10, now=100) is True
    assert store.claim_community_build(ROOT, version, "replacement", 10, now=109.9) is False
    assert store.claim_community_build(ROOT, version, "replacement", 10, now=110) is True

    assert store.complete_community_build(ROOT, version, "crashed-worker") is False
    assert store.complete_community_build(ROOT, version, "replacement") is True


def test_version_advance_makes_historical_state_ineligible(tmp_path):
    store = GraphStore(str(tmp_path))
    old_version = _dirty_generation(store)
    assert store.claim_community_build(ROOT, old_version, "old-worker", 60, now=100) is True

    new_version = store.mark_communities_dirty(ROOT)
    assert new_version > old_version
    assert store.complete_community_build(ROOT, old_version, "old-worker") is False
    assert store.fail_community_build(ROOT, old_version, "old-worker") == (False, False)
    assert store.claim_community_build(ROOT, old_version, "old-retry", 60, now=101) is False
    assert store.claim_community_build(ROOT, new_version, "new-worker", 60, now=101) is True
