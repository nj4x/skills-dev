"""
Tests for the report-generation CAS operations on vectors.graph_store.GraphStore.

Covers the 4 atomic domain operations that replaced the reports_* getter/setter
pairs — claim_report_build, commit_report_build, clear_report_claim, and
report_build_status — plus the discard-and-recreate schema migration (v2).
Each test gets its own tempdir so SQLite files are isolated.
"""

from __future__ import annotations

import sqlite3
import time

from vectors.graph_store import GraphStore, ReportBuildStatus


ROOT = "test_reports_root_id_abc123"


def make_store(tmp_path) -> GraphStore:
    return GraphStore(str(tmp_path))


# ---------------------------------------------------------------------------
# claim_report_build
# ---------------------------------------------------------------------------

def test_claim_report_build_happy_path(tmp_path):
    """A first claim against an uncommitted build returns a token string."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    assert isinstance(token, str)
    assert token


def test_claim_report_build_none_when_already_committed(tmp_path):
    """Claiming a build whose reports are already committed returns None."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    assert token is not None
    assert gs.commit_report_build(ROOT, "build-1", token) is True

    # Same build_id is already committed → no work to do.
    assert gs.claim_report_build(ROOT, "build-1", 60) is None


def test_claim_report_build_none_when_live_same_generation_claim(tmp_path):
    """A live (unexpired) same-generation claim blocks a second claim."""
    gs = make_store(tmp_path)
    first = gs.claim_report_build(ROOT, "build-1", 600)
    assert first is not None

    # Same build_id, lease still live → back off.
    assert gs.claim_report_build(ROOT, "build-1", 600) is None


def test_claim_report_build_supersedes_prior_generation(tmp_path):
    """A different build_id supersedes an existing live claim unconditionally."""
    gs = make_store(tmp_path)
    first = gs.claim_report_build(ROOT, "build-1", 600)
    assert first is not None

    # Different build_id (detection advanced) → new claim wins even though the
    # prior lease has not expired.
    second = gs.claim_report_build(ROOT, "build-2", 600)
    assert second is not None
    assert second != first


def test_claim_report_build_reclaims_expired_same_generation(tmp_path):
    """An expired same-generation claim can be reclaimed with a fresh token."""
    gs = make_store(tmp_path)
    first = gs.claim_report_build(ROOT, "build-1", 60)
    assert first is not None

    # Force the lease into the past so the same-generation guard sees it expired.
    conn = sqlite3.connect(gs._db_path(ROOT))
    try:
        conn.execute(
            "UPDATE meta SET reports_claim_expires_at=? WHERE root_id=?",
            (time.time() - 1.0, ROOT),
        )
        conn.commit()
    finally:
        conn.close()

    second = gs.claim_report_build(ROOT, "build-1", 60)
    assert second is not None
    assert second != first


# ---------------------------------------------------------------------------
# commit_report_build
# ---------------------------------------------------------------------------

def test_commit_report_build_applies_on_token_match(tmp_path):
    """commit_report_build succeeds when the token matches and updates status."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    assert gs.commit_report_build(ROOT, "build-1", token) is True

    status = gs.report_build_status(ROOT)
    assert status.committed_build_id == "build-1"
    assert status.dirty is False
    assert status.claimed_build_id is None
    assert status.claim_expires_at is None


def test_commit_report_build_false_on_wrong_token(tmp_path):
    """commit_report_build returns False when the token does not match."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    assert token is not None
    assert gs.commit_report_build(ROOT, "build-1", "not-the-token") is False

    # Slot remains claimed (uncommitted) after a rejected commit.
    status = gs.report_build_status(ROOT)
    assert status.committed_build_id is None
    assert status.claimed_build_id == "build-1"


def test_commit_report_build_false_on_superseded_build_id(tmp_path):
    """commit_report_build returns False when a newer build_id has superseded the claim."""
    gs = make_store(tmp_path)
    token_a = gs.claim_report_build(ROOT, "build-1", 60)
    assert token_a is not None

    # Detection advances; build-2 supersedes the prior claim unconditionally.
    token_b = gs.claim_report_build(ROOT, "build-2", 60)
    assert token_b is not None
    assert token_b != token_a

    # Original worker tries to commit build-1 with its now-stale token.
    assert gs.commit_report_build(ROOT, "build-1", token_a) is False

    # Slot still reflects the live build-2 claim; nothing was committed.
    status = gs.report_build_status(ROOT)
    assert status.committed_build_id is None
    assert status.claimed_build_id == "build-2"


# ---------------------------------------------------------------------------
# clear_report_claim
# ---------------------------------------------------------------------------

def test_clear_report_claim_clears_on_match(tmp_path):
    """clear_report_claim releases the slot when the token matches."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    assert gs.clear_report_claim(ROOT, token) is True

    status = gs.report_build_status(ROOT)
    assert status.claimed_build_id is None
    assert status.claim_expires_at is None


def test_clear_report_claim_noop_on_wrong_token(tmp_path):
    """clear_report_claim returns False and leaves the claim intact on mismatch."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    assert token is not None
    assert gs.clear_report_claim(ROOT, "wrong-token") is False

    status = gs.report_build_status(ROOT)
    assert status.claimed_build_id == "build-1"


# ---------------------------------------------------------------------------
# report_build_status
# ---------------------------------------------------------------------------

def test_report_build_status_reflects_committed_state(tmp_path):
    """After commit, status reports the committed build and not dirty."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-committed", 60)
    gs.commit_report_build(ROOT, "build-committed", token)

    status = gs.report_build_status(ROOT)
    assert status.committed_build_id == "build-committed"
    assert status.dirty is False


def test_report_build_status_dirty_before_any_commit(tmp_path):
    """A freshly created root reports dirty=True and no committed build."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)
    status = gs.report_build_status(ROOT)
    assert status.dirty is True
    assert status.committed_build_id is None


def test_report_build_status_reflects_claimed_state(tmp_path):
    """A live claim is reflected with claimed_build_id and a future expiry."""
    gs = make_store(tmp_path)
    before = time.time()
    gs.claim_report_build(ROOT, "build-claimed", 600)

    status = gs.report_build_status(ROOT)
    assert status.claimed_build_id == "build-claimed"
    assert status.claim_expires_at is not None
    assert status.claim_expires_at > before


def test_report_build_status_unclaimed_after_clear(tmp_path):
    """After clearing a claim, status reports an unclaimed slot."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "build-1", 60)
    gs.clear_report_claim(ROOT, token)

    status = gs.report_build_status(ROOT)
    assert status.claimed_build_id is None
    assert status.claim_expires_at is None


def test_report_build_status_type(tmp_path):
    """report_build_status returns a ReportBuildStatus dataclass."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)
    assert isinstance(gs.report_build_status(ROOT), ReportBuildStatus)


# ---------------------------------------------------------------------------
# Schema migration (v2 discard-and-recreate)
# ---------------------------------------------------------------------------

def test_schema_migration_drops_and_recreates(tmp_path):
    # Create a fake old-schema DB with the removed reports_claim_lease_seconds column.
    db_path = GraphStore(str(tmp_path))._db_path("root-migration-test")
    old_meta_ddl = """
    CREATE TABLE meta (
      root_id TEXT PRIMARY KEY,
      communities_dirty INTEGER DEFAULT 0,
      graph_version INTEGER NOT NULL DEFAULT 0,
      communities_version INTEGER NOT NULL DEFAULT 0,
      committed_build_id TEXT,
      reports_version INTEGER DEFAULT 0,
      reports_dirty INTEGER DEFAULT 1,
      reports_committed_build_id TEXT,
      reports_claimed_build_id TEXT,
      reports_claim_lease_seconds INTEGER
    );
    """
    conn = sqlite3.connect(db_path)
    conn.executescript(old_meta_ddl)
    conn.execute("INSERT INTO meta (root_id) VALUES ('root-migration-test')")
    conn.commit()
    conn.close()

    # Opening via GraphStore should trigger migration.
    gs = GraphStore(str(tmp_path))
    gs._ensure_schema("root-migration-test")

    # Verify old column gone, new columns present.
    conn2 = sqlite3.connect(db_path)
    conn2.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn2.execute("PRAGMA table_info(meta)").fetchall()}
    conn2.close()

    assert "reports_claim_lease_seconds" not in cols
    assert "reports_claim_expires_at" in cols
    assert "reports_claim_token" in cols

    # reports_dirty should be True (default) after migration.
    status = gs.report_build_status("root-migration-test")
    assert status.dirty is True


def test_migration_is_idempotent(tmp_path):
    """Ensuring the schema twice on a fresh DB must not error and stays dirty."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)
    gs._ensure_schema(ROOT)
    assert gs.report_build_status(ROOT).dirty is True


def test_communities_have_report_build_id_column(tmp_path):
    """The communities table still carries a report_build_id column."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)

    conn = sqlite3.connect(gs._db_path(ROOT))
    conn.row_factory = sqlite3.Row
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(communities)").fetchall()}
    finally:
        conn.close()
    assert "report_build_id" in cols


# ---------------------------------------------------------------------------
# Staleness detection via report_build_id comparison (unchanged behaviour)
# ---------------------------------------------------------------------------

def _report_build_id(gs: GraphStore, root_id: str, community_id: str) -> str | None:
    conn = sqlite3.connect(gs._db_path(root_id))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT report_build_id FROM communities WHERE id=? AND root_id=?",
            (community_id, root_id),
        ).fetchone()
        return row["report_build_id"] if row else None
    finally:
        conn.close()


def test_report_build_id_mismatch_is_stale(tmp_path):
    """A stored report whose report_build_id differs from the committed detection
    build_id is identifiable as stale."""
    gs = make_store(tmp_path)
    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    version = gs.get_graph_version(ROOT)

    communities = [
        {
            "community_id": "c1",
            "level": 0,
            "entity_ids": [],
            "report_build_id": "old-report-build",
        }
    ]
    assert gs.replace_communities_if_current(ROOT, version, "detect-build-2", communities) is True

    _, committed_build_id = gs.get_committed_generation(ROOT)
    assert committed_build_id == "detect-build-2"

    stored_report_build_id = _report_build_id(gs, ROOT, "c1")
    assert stored_report_build_id == "old-report-build"
    assert stored_report_build_id != committed_build_id


def test_matching_report_build_id_is_fresh(tmp_path):
    """A stored report whose report_build_id matches the committed build is fresh."""
    gs = make_store(tmp_path)
    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    version = gs.get_graph_version(ROOT)

    communities = [
        {
            "community_id": "c1",
            "level": 0,
            "entity_ids": [],
            "report_build_id": "detect-build-7",
        }
    ]
    assert gs.replace_communities_if_current(ROOT, version, "detect-build-7", communities) is True

    _, committed_build_id = gs.get_committed_generation(ROOT)
    assert _report_build_id(gs, ROOT, "c1") == committed_build_id


def test_reports_state_is_durable_across_reopen(tmp_path):
    """Committed report state persists when the store is reopened."""
    gs = make_store(tmp_path)
    token = gs.claim_report_build(ROOT, "committed-1", 120)
    gs.commit_report_build(ROOT, "committed-1", token)

    reopened = GraphStore(str(tmp_path))
    status = reopened.report_build_status(ROOT)
    assert status.committed_build_id == "committed-1"
    assert status.dirty is False
    assert status.claimed_build_id is None
