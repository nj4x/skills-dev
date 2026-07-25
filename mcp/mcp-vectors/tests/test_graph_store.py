"""
Tests for vectors.graph_store.GraphStore.

Each test gets its own tempdir so SQLite files are isolated.
"""

from __future__ import annotations

import json
import os
import tempfile
import types

import pytest

from vectors.graph_store import GraphStore, entity_id


ROOT = "test_root_id_abc123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store(tmp_path) -> GraphStore:
    return GraphStore(str(tmp_path))


def _make_entity_map(entities_data, edges_data):
    """Build a minimal EntityMap-like object from plain dicts."""

    def _make_entity(d):
        e = types.SimpleNamespace()
        e.name = d["name"]
        e.type = d["type"]
        e.description = d.get("description", "")
        e.chunk_id = d.get("chunk_id")
        return e

    def _make_edge(d):
        ed = types.SimpleNamespace()
        ed.source = d["source"]
        ed.target = d["target"]
        ed.source_type = d.get("source_type", "unknown")
        ed.target_type = d.get("target_type", "unknown")
        ed.edge_type = d["edge_type"]
        ed.weight = d.get("weight", 1.0)
        ed.description = d.get("description", "")
        return ed

    em = types.SimpleNamespace()
    em.entities = [_make_entity(e) for e in entities_data]
    em.edges = [_make_edge(e) for e in edges_data]
    return em


# ---------------------------------------------------------------------------
# test_merge_entity_dedup
# ---------------------------------------------------------------------------

def test_merge_entity_dedup(tmp_path):
    """Merging the same entity twice must give frequency=2 with one row."""
    gs = make_store(tmp_path)

    eid1 = gs.merge_entity("MyClass", "class", "A class", ROOT, "/src/a.py")
    eid2 = gs.merge_entity("MyClass", "class", "A class", ROOT, "/src/a.py")

    assert eid1 == eid2, "Same entity should produce the same ID"

    results = gs.find_entities("myclass", ROOT, limit=10)
    assert len(results) == 1, "Should be exactly one row"
    assert results[0]["frequency"] == 2, "Frequency should be incremented to 2"


# ---------------------------------------------------------------------------
# test_merge_entity_different_type
# ---------------------------------------------------------------------------

def test_merge_entity_different_type(tmp_path):
    """Same name but different type produces two distinct entity rows."""
    gs = make_store(tmp_path)

    eid_class = gs.merge_entity("parse", "function", "A function", ROOT, "/src/a.py")
    eid_fn = gs.merge_entity("parse", "module", "A module", ROOT, "/src/b.py")

    assert eid_class != eid_fn, "Different types must produce different IDs"

    results = gs.find_entities("parse", ROOT, limit=10)
    assert len(results) == 2, "Should have two rows for same name but different types"


# ---------------------------------------------------------------------------
# test_delete_file_entities_orphan
# ---------------------------------------------------------------------------

def test_delete_file_entities_orphan(tmp_path):
    """If entity has only one source file, deleting that file removes the entity."""
    gs = make_store(tmp_path)
    gs.merge_entity("OrphanClass", "class", "", ROOT, "/src/orphan.py")

    gs.delete_file_entities("/src/orphan.py", ROOT)

    results = gs.find_entities("orphanclass", ROOT)
    assert results == [], "Entity should be deleted when its only file is removed"


# ---------------------------------------------------------------------------
# test_delete_file_entities_shared
# ---------------------------------------------------------------------------

def test_delete_file_entities_shared(tmp_path):
    """Entity with two source files: removing one keeps entity but updates file list."""
    gs = make_store(tmp_path)

    gs.merge_entity("SharedClass", "class", "", ROOT, "/src/a.py")
    gs.merge_entity("SharedClass", "class", "", ROOT, "/src/b.py")

    gs.delete_file_entities("/src/a.py", ROOT)

    results = gs.find_entities("sharedclass", ROOT)
    assert len(results) == 1, "Entity should still exist"

    fps = json.loads(results[0]["file_paths"])
    assert "/src/a.py" not in fps, "/src/a.py should have been removed"
    assert "/src/b.py" in fps, "/src/b.py should remain"


# ---------------------------------------------------------------------------
# test_find_entities_fuzzy
# ---------------------------------------------------------------------------

def test_find_entities_fuzzy(tmp_path):
    """LIKE search should return matching entities and exclude non-matching ones."""
    gs = make_store(tmp_path)

    gs.merge_entity("FooBarBaz", "class", "", ROOT, "/a.py")
    gs.merge_entity("BarHelper", "function", "", ROOT, "/b.py")
    gs.merge_entity("Unrelated", "class", "", ROOT, "/c.py")

    results = gs.find_entities("bar", ROOT, limit=10)
    names = {r["name"] for r in results}

    assert "FooBarBaz" in names, "FooBarBaz contains 'bar'"
    assert "BarHelper" in names, "BarHelper contains 'bar'"
    assert "Unrelated" not in names, "Unrelated should not match 'bar'"


def test_find_entities_case_insensitive(tmp_path):
    """LIKE search must be case-insensitive."""
    gs = make_store(tmp_path)
    gs.merge_entity("UserService", "class", "", ROOT, "/a.py")

    upper = gs.find_entities("USERSERVICE", ROOT)
    lower = gs.find_entities("userservice", ROOT)
    mixed = gs.find_entities("UserService", ROOT)

    assert len(upper) == 1
    assert len(lower) == 1
    assert len(mixed) == 1


# ---------------------------------------------------------------------------
# test_get_neighbors_single_hop
# ---------------------------------------------------------------------------

def test_get_neighbors_single_hop(tmp_path):
    """Graph A→B→C; neighbors of A at depth=1 should be [B] only."""
    gs = make_store(tmp_path)

    # Build entities first
    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    gs.merge_entity("B", "function", "", ROOT, "/b.py")
    gs.merge_entity("C", "function", "", ROOT, "/c.py")

    # A→B
    gs.merge_edge("A", "B", "function", "function", "calls", ROOT)
    # B→C
    gs.merge_edge("B", "C", "function", "function", "calls", ROOT)

    a_id = entity_id("A", "function", ROOT)
    neighbors = gs.get_neighbors(a_id, max_depth=1)
    neighbor_names = {n["name"] for n in neighbors}

    assert "B" in neighbor_names, "B should be a depth-1 neighbor of A"
    assert "C" not in neighbor_names, "C is depth-2 from A; should not appear at depth=1"
    assert "A" not in neighbor_names, "Seed entity itself should be excluded"


def test_get_neighbors_two_hop(tmp_path):
    """Graph A→B→C; neighbors of A at depth=2 should include both B and C."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    gs.merge_entity("B", "function", "", ROOT, "/b.py")
    gs.merge_entity("C", "function", "", ROOT, "/c.py")
    gs.merge_edge("A", "B", "function", "function", "calls", ROOT)
    gs.merge_edge("B", "C", "function", "function", "calls", ROOT)

    a_id = entity_id("A", "function", ROOT)
    neighbors = gs.get_neighbors(a_id, max_depth=2)
    neighbor_names = {n["name"] for n in neighbors}

    assert "B" in neighbor_names
    assert "C" in neighbor_names
    assert "A" not in neighbor_names


def test_get_neighbors_edge_type_filter(tmp_path):
    """Edge type filter should exclude edges of other types."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "class", "", ROOT, "/a.py")
    gs.merge_entity("B", "class", "", ROOT, "/b.py")
    gs.merge_entity("C", "module", "", ROOT, "/c.py")

    gs.merge_edge("A", "B", "class", "class", "inherits", ROOT)
    gs.merge_edge("A", "C", "class", "module", "imports", ROOT)

    a_id = entity_id("A", "class", ROOT)
    neighbors = gs.get_neighbors(a_id, max_depth=1, edge_types=["inherits"])
    neighbor_names = {n["name"] for n in neighbors}

    assert "B" in neighbor_names, "B reachable via 'inherits'"
    assert "C" not in neighbor_names, "C only reachable via 'imports', should be filtered"


# ---------------------------------------------------------------------------
# test_get_callers
# ---------------------------------------------------------------------------

def test_get_callers(tmp_path):
    """get_callers should return entities that have a 'calls' edge to function_name."""
    gs = make_store(tmp_path)

    gs.merge_entity("helper", "function", "", ROOT, "/lib.py")
    gs.merge_entity("main", "function", "", ROOT, "/main.py")
    gs.merge_entity("setup", "function", "", ROOT, "/setup.py")
    gs.merge_entity("unrelated", "function", "", ROOT, "/other.py")

    # main calls helper
    gs.merge_edge("main", "helper", "function", "function", "calls", ROOT)
    # setup calls helper
    gs.merge_edge("setup", "helper", "function", "function", "calls", ROOT)
    # unrelated imports helper (not a calls edge)
    gs.merge_edge("unrelated", "helper", "function", "function", "imports", ROOT)

    callers = gs.get_callers("helper", ROOT)
    caller_names = {c["name"] for c in callers}

    assert "main" in caller_names
    assert "setup" in caller_names
    assert "unrelated" not in caller_names, "imports edge should not count as a caller"
    assert "helper" not in caller_names, "target itself should not appear"


def test_get_callers_none(tmp_path):
    """get_callers returns empty list when function is not found."""
    gs = make_store(tmp_path)
    result = gs.get_callers("nonexistent_fn", ROOT)
    assert result == []


# ---------------------------------------------------------------------------
# test_dirty_flag
# ---------------------------------------------------------------------------

def test_dirty_flag(tmp_path):
    """mark → check True → clear with replace_communities_if_current → check False."""
    gs = make_store(tmp_path)

    # Initially dirty (no committed_build_id)
    assert gs.are_communities_dirty(ROOT) is True

    # Add some data
    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    version = gs.get_graph_version(ROOT)
    assert gs.are_communities_dirty(ROOT) is True

    # Replace communities to mark as clean
    result = gs.replace_communities_if_current(ROOT, version, "build_1", [])
    assert result is True

    # Now not dirty (committed_build_id is set and versions match)
    assert gs.are_communities_dirty(ROOT) is False

    # Mark dirty again
    gs.mark_communities_dirty(ROOT)
    assert gs.are_communities_dirty(ROOT) is True


def test_dirty_flag_set_by_delete_file(tmp_path):
    """delete_file_entities must mark communities dirty."""
    gs = make_store(tmp_path)
    gs.merge_entity("X", "class", "", ROOT, "/x.py")

    # Mark clean by committing communities
    version = gs.get_graph_version(ROOT)
    gs.replace_communities_if_current(ROOT, version, "build_1", [])
    assert gs.are_communities_dirty(ROOT) is False

    # Delete entity should mark dirty again
    gs.delete_file_entities("/x.py", ROOT)
    assert gs.are_communities_dirty(ROOT) is True


# ---------------------------------------------------------------------------
# test_rebuild_degree
# ---------------------------------------------------------------------------

def test_rebuild_degree(tmp_path):
    """After adding edges, rebuild_degree should set correct degree values."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    gs.merge_entity("B", "function", "", ROOT, "/b.py")
    gs.merge_entity("C", "function", "", ROOT, "/c.py")

    # A→B, A→C  — A has degree 2, B and C have degree 1 each
    gs.merge_edge("A", "B", "function", "function", "calls", ROOT)
    gs.merge_edge("A", "C", "function", "function", "calls", ROOT)

    gs.rebuild_degree(ROOT)

    a_id = entity_id("A", "function", ROOT)
    b_id = entity_id("B", "function", ROOT)
    c_id = entity_id("C", "function", ROOT)

    entities = gs.find_entities("", ROOT, limit=100)  # wildcard
    by_id = {e["id"]: e for e in entities}

    assert by_id[a_id]["degree"] == 2, "A participates in 2 edges"
    assert by_id[b_id]["degree"] == 1, "B participates in 1 edge"
    assert by_id[c_id]["degree"] == 1, "C participates in 1 edge"


# ---------------------------------------------------------------------------
# test_merge_entity_map
# ---------------------------------------------------------------------------

def test_merge_entity_map(tmp_path):
    """merge_entity_map should insert all entities+edges and mark dirty."""
    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[
            {"name": "Alpha", "type": "class"},
            {"name": "Beta", "type": "class"},
        ],
        edges_data=[
            {
                "source": "Alpha",
                "target": "Beta",
                "source_type": "class",
                "target_type": "class",
                "edge_type": "inherits",
            }
        ],
    )

    gs.merge_entity_map(em, ROOT, "/src/file.py")

    stats = gs.get_stats(ROOT)
    assert stats["entity_count"] == 2
    assert stats["edge_count"] == 1
    assert stats["communities_dirty"] is True


# ---------------------------------------------------------------------------
# test_get_stats
# ---------------------------------------------------------------------------

def test_get_stats_empty(tmp_path):
    """get_stats on an empty root returns zeros."""
    gs = make_store(tmp_path)
    stats = gs.get_stats(ROOT)
    assert stats["entity_count"] == 0
    assert stats["edge_count"] == 0
    assert stats["community_count"] == 0
    assert stats["communities_dirty"] is False
    assert "graph_version" in stats
    assert "communities_version" in stats


# ---------------------------------------------------------------------------
# test_edge_weight_accumulation
# ---------------------------------------------------------------------------

def test_edge_weight_accumulation(tmp_path):
    """Merging the same edge twice should accumulate weight."""
    gs = make_store(tmp_path)

    gs.merge_entity("X", "function", "", ROOT, "/x.py")
    gs.merge_entity("Y", "function", "", ROOT, "/y.py")
    gs.merge_edge("X", "Y", "function", "function", "calls", ROOT, weight=1.0)
    gs.merge_edge("X", "Y", "function", "function", "calls", ROOT, weight=2.5)

    # Read back via find_entities + separate edge check (direct sqlite)
    import sqlite3
    from vectors.graph_store import entity_id, edge_id
    x_id = entity_id("X", "function", ROOT)
    y_id = entity_id("Y", "function", ROOT)
    e_id = edge_id(x_id, y_id, "calls", ROOT)

    db_path = gs._db_path(ROOT)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT weight FROM edges WHERE id = ?", (e_id,)).fetchone()
    conn.close()

    assert row is not None
    assert abs(row["weight"] - 3.5) < 1e-9, f"Expected weight 3.5, got {row['weight']}"


# ---------------------------------------------------------------------------
# Phase 2 tests
# ---------------------------------------------------------------------------

def test_read_graph_snapshot(tmp_path):
    """read_graph_snapshot returns consistent snapshot in single transaction."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    gs.merge_entity("B", "function", "", ROOT, "/b.py")
    gs.merge_edge("A", "B", "function", "function", "calls", ROOT)

    snapshot = gs.read_graph_snapshot(ROOT)
    assert snapshot.root_id == ROOT
    assert snapshot.graph_version >= 0
    assert len(snapshot.entities) == 2
    assert len(snapshot.edges) == 1


@pytest.mark.skipif(True, reason="networkx installed in Phase 2B")
def test_to_networkx(tmp_path):
    """to_networkx converts snapshot to networkx DiGraph."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    gs.merge_entity("B", "function", "", ROOT, "/b.py")
    gs.merge_edge("A", "B", "function", "function", "calls", ROOT)

    snapshot = gs.read_graph_snapshot(ROOT)
    g = gs.to_networkx(snapshot)

    assert len(g.nodes()) == 2
    assert len(g.edges()) == 1
    assert g.has_edge(list(snapshot.edges)[0]["source_id"], list(snapshot.edges)[0]["target_id"])


def test_get_graph_version(tmp_path):
    """get_graph_version returns current version."""
    gs = make_store(tmp_path)
    v = gs.get_graph_version(ROOT)
    assert isinstance(v, int)
    assert v >= 0


def test_get_committed_generation(tmp_path):
    """get_committed_generation returns (communities_version, build_id)."""
    gs = make_store(tmp_path)
    version, build_id = gs.get_committed_generation(ROOT)
    assert isinstance(version, int)
    assert build_id is None


def test_has_root(tmp_path):
    """has_root returns False for nonexistent roots."""
    gs = make_store(tmp_path)
    assert gs.has_root(ROOT) is False

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    assert gs.has_root(ROOT) is True


def test_drop_root_removes_file_and_has_root_returns_false(tmp_path):
    """drop_root deletes the sqlite file; has_root returns False afterwards."""
    gs = make_store(tmp_path)
    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    assert gs.has_root(ROOT) is True

    db_path = gs._db_path(ROOT)
    assert os.path.exists(db_path)

    gs.drop_root(ROOT)

    assert gs.has_root(ROOT) is False
    assert not os.path.exists(db_path)


def test_drop_root_removes_wal_shm_sidecars(tmp_path):
    """drop_root removes -wal and -shm sidecar files alongside the main sqlite."""
    gs = make_store(tmp_path)
    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    db_path = gs._db_path(ROOT)
    wal_path = db_path + "-wal"
    shm_path = db_path + "-shm"
    # Create stub sidecar files to simulate WAL mode residues.
    open(wal_path, "w").close()
    open(shm_path, "w").close()

    gs.drop_root(ROOT)

    assert not os.path.exists(db_path)
    assert not os.path.exists(wal_path)
    assert not os.path.exists(shm_path)


def test_drop_root_idempotent(tmp_path):
    """drop_root on a nonexistent root is a no-op."""
    gs = make_store(tmp_path)
    gs.drop_root(ROOT)  # must not raise
    assert gs.has_root(ROOT) is False


def test_drop_root_removes_registry_entry(tmp_path):
    """drop_root removes the root entry from registry.txt."""
    gs = make_store(tmp_path)
    gs.merge_entity("A", "function", "", ROOT, "/a.py")

    registry_path = os.path.join(str(tmp_path), "registry.txt")
    with open(registry_path) as fh:
        before = fh.read()
    assert ROOT in before

    gs.drop_root(ROOT)

    try:
        with open(registry_path) as fh:
            after = fh.read()
    except FileNotFoundError:
        after = ""
    assert ROOT not in after


def test_are_communities_dirty_with_version_mismatch(tmp_path):
    """are_communities_dirty returns True when graph_version != communities_version."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    # After merge, graph_version > communities_version
    assert gs.are_communities_dirty(ROOT) is True


def test_replace_communities_if_current_success(tmp_path):
    """replace_communities_if_current succeeds when version matches and build_id is NULL."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    version = gs.get_graph_version(ROOT)

    communities = [
        {
            "community_id": "c1",
            "level": 0,
            "parent_id": None,
            "entity_ids": ["A"],
            "file_ids": [],
            "summary": "Test community",
            "report_emb_id": None,
        }
    ]

    result = gs.replace_communities_if_current(ROOT, version, "build_1", communities)
    assert result is True

    v, build_id = gs.get_committed_generation(ROOT)
    assert v == version
    assert build_id == "build_1"


def test_replace_communities_if_current_version_mismatch(tmp_path):
    """replace_communities_if_current returns False on version mismatch."""
    gs = make_store(tmp_path)

    result = gs.replace_communities_if_current(ROOT, 999, "build_1", [])
    assert result is False


def test_invalidate_communities(tmp_path):
    """invalidate_communities clears committed build_id without changing graph_version."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")
    version = gs.get_graph_version(ROOT)

    communities = [{"community_id": "c1", "level": 0, "entity_ids": []}]
    gs.replace_communities_if_current(ROOT, version, "build_1", communities)

    gs.invalidate_communities(ROOT)

    v, build_id = gs.get_committed_generation(ROOT)
    assert v == 0  # communities_version reset
    assert build_id is None


def test_list_dirty_roots(tmp_path):
    """list_dirty_roots returns only dirty roots."""
    gs = make_store(tmp_path)

    gs.merge_entity("A", "function", "", ROOT, "/a.py")

    dirty_roots = gs.list_dirty_roots()
    assert ROOT in dirty_roots


def test_replace_file_entity_map_returns_version(tmp_path):
    """replace_file_entity_map returns new graph_version."""
    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "A", "type": "function"}],
        edges_data=[],
    )

    version, _, _ = gs.replace_file_entity_map(em, ROOT, "/file.py")
    assert isinstance(version, int)
    assert version > 0


def test_delete_file_entities_returns_version(tmp_path):
    """delete_file_entities returns new graph_version or 0 for no-op."""
    gs = make_store(tmp_path)

    # No-op: no entities for file
    v = gs.delete_file_entities("/nonexistent.py", ROOT)
    assert v == 0

    # Real delete
    gs.merge_entity("A", "function", "", ROOT, "/file.py")
    v = gs.delete_file_entities("/file.py", ROOT)
    assert v > 0


def test_mark_communities_dirty_returns_version(tmp_path):
    """mark_communities_dirty returns new graph_version."""
    gs = make_store(tmp_path)

    v = gs.mark_communities_dirty(ROOT)
    assert isinstance(v, int)
    assert v > 0


# ---------------------------------------------------------------------------
# Phase 2 autofix regression tests
# ---------------------------------------------------------------------------

def test_cas_deadlock_replace_file_resets_committed_build_id(tmp_path):
    """C1 — replace_file_entity_map must reset committed_build_id so CAS accepts the next build.

    Scenario:
      1. Index file A → graph_version = v0
      2. Commit communities for v0 → committed_build_id = "build_0"
      3. Re-index file A → graph_version = v1, committed_build_id must be NULL
      4. replace_communities_if_current with expected_version=v1 must return True
    """
    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "X", "type": "function"}],
        edges_data=[],
    )

    # Step 1: first index
    v0, _, _ = gs.replace_file_entity_map(em, ROOT, "/a.py")
    assert v0 > 0

    # Step 2: commit communities
    ok = gs.replace_communities_if_current(ROOT, v0, "build_0", [{"community_id": "c0", "level": 0, "entity_ids": []}])
    assert ok is True, "First CAS must succeed"

    # Step 3: re-index the same file — this must bump graph_version AND clear committed_build_id
    v1, _, _ = gs.replace_file_entity_map(em, ROOT, "/a.py")
    assert v1 > v0, "graph_version must increment on re-index"

    # Step 4: CAS for the new version must succeed (committed_build_id should now be NULL)
    ok2 = gs.replace_communities_if_current(ROOT, v1, "build_1", [{"community_id": "c1", "level": 0, "entity_ids": []}])
    assert ok2 is True, "Second CAS deadlocked — committed_build_id was not reset on graph mutation (C1 regression)"


def test_cas_deadlock_delete_file_resets_committed_build_id(tmp_path):
    """C1 — delete_file_entities must also reset committed_build_id."""
    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "Y", "type": "function"}],
        edges_data=[],
    )

    v0, _, _ = gs.replace_file_entity_map(em, ROOT, "/b.py")
    gs.replace_file_entity_map(
        _make_entity_map(entities_data=[{"name": "Z", "type": "function"}], edges_data=[]),
        ROOT, "/c.py",
    )
    # Use the latest graph_version after both files are indexed
    v_before = gs.get_graph_version(ROOT)
    ok = gs.replace_communities_if_current(ROOT, v_before, "build_x", [])
    assert ok is True

    # Delete one of the files
    v_after = gs.delete_file_entities("/b.py", ROOT)
    assert v_after > v_before

    # CAS for new version must succeed
    ok2 = gs.replace_communities_if_current(ROOT, v_after, "build_y", [])
    assert ok2 is True, "CAS after delete deadlocked — committed_build_id was not reset (C1 regression)"


def test_toctou_cas_only_one_concurrent_caller_wins(tmp_path):
    """Correctness 1 — exactly one of two concurrent replace_communities_if_current calls returns True."""
    import threading

    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "A", "type": "function"}],
        edges_data=[],
    )
    version, _, _ = gs.replace_file_entity_map(em, ROOT, "/a.py")

    results = []
    barrier = threading.Barrier(2)

    def try_commit(build_id):
        barrier.wait()  # both threads start at the same time
        r = gs.replace_communities_if_current(ROOT, version, build_id, [])
        results.append(r)

    t1 = threading.Thread(target=try_commit, args=("build_A",))
    t2 = threading.Thread(target=try_commit, args=("build_B",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results.count(True) == 1, (
        f"Expected exactly one winner, got results={results} (TOCTOU regression)"
    )
    assert results.count(False) == 1


def test_phantom_edges_sentinel_cleaned_on_entity_delete(tmp_path):
    """Correctness 2 — Deleting a file must also remove sentinel edge_contributions.

    Scenario:
      1. File A contributes edge E(X→Y) with explicit entity types so the edge
         source/target IDs match the entity IDs (no separate stub entity).
      2. File B contributes the same edge E(X→Y).
      3. Delete file A → edge E must persist (B still contributes it).
      4. Delete file B → edge E must be gone (no contributor remains).
      5. Additionally, if a sentinel contribution exists for a deleted entity, it
         must also be removed to prevent phantom edge resurrection.
    """
    import sqlite3

    gs = make_store(tmp_path)

    # Use explicit source_type / target_type = "function" so that the edge IDs
    # match the entity IDs computed from the entity list (avoiding the stub-entity
    # mismatch that would occur with the default type="unknown").
    em_a = _make_entity_map(
        entities_data=[{"name": "X", "type": "function"}, {"name": "Y", "type": "function"}],
        edges_data=[{"source": "X", "target": "Y", "edge_type": "calls",
                     "source_type": "function", "target_type": "function"}],
    )
    em_b = _make_entity_map(
        entities_data=[{"name": "X", "type": "function"}, {"name": "Y", "type": "function"}],
        edges_data=[{"source": "X", "target": "Y", "edge_type": "calls",
                     "source_type": "function", "target_type": "function"}],
    )

    gs.replace_file_entity_map(em_a, ROOT, "/a.py")
    gs.replace_file_entity_map(em_b, ROOT, "/b.py")

    db_path = gs._db_path(ROOT)

    # Verify edge E exists with two contributions
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    edges_before = conn.execute("SELECT COUNT(*) FROM edges WHERE root_id=?", (ROOT,)).fetchone()[0]
    contribs_before = conn.execute(
        "SELECT COUNT(*) FROM edge_contributions WHERE root_id=?", (ROOT,)
    ).fetchone()[0]
    conn.close()
    assert edges_before >= 1, "Edge E should exist after indexing two files"
    assert contribs_before == 2, f"Expected 2 contributions (A and B), got {contribs_before}"

    # Delete file A — edge E must persist because B still contributes
    gs.delete_file_entities("/a.py", ROOT)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    edges_mid = conn.execute("SELECT COUNT(*) FROM edges WHERE root_id=?", (ROOT,)).fetchone()[0]
    contribs_mid = conn.execute(
        "SELECT COUNT(*) FROM edge_contributions WHERE root_id=?", (ROOT,)
    ).fetchone()[0]
    conn.close()
    assert edges_mid >= 1, "Edge E must persist when contributor B still exists (phantom edge mid)"
    assert contribs_mid == 1, f"Expected 1 remaining contribution after deleting A, got {contribs_mid}"

    # Delete file B — now edge E must disappear entirely
    gs.delete_file_entities("/b.py", ROOT)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    edges_after = conn.execute("SELECT COUNT(*) FROM edges WHERE root_id=?", (ROOT,)).fetchone()[0]
    sentinel_after = conn.execute(
        "SELECT COUNT(*) FROM edge_contributions WHERE root_id=? AND file_path=''", (ROOT,)
    ).fetchone()[0]
    conn.close()

    assert edges_after == 0, (
        f"Edge E persists after all contributors removed ({edges_after} remain) — phantom edge regression"
    )
    assert sentinel_after == 0, (
        f"{sentinel_after} orphan sentinel contribution(s) remain — phantom sentinel regression"
    )


def test_phantom_edges_manual_sentinel_cleaned_when_entity_deleted(tmp_path):
    """Correctness 2 (sentinel path) — sentinel contributions are purged when entity is deleted.

    Manually inserts a sentinel contribution to simulate data migrated from an older
    schema.  After deleting the entity that the sentinel references, the sentinel must
    also be gone.
    """
    import sqlite3
    from vectors.graph_store import entity_id, edge_id, MIGRATION_SENTINEL_FILE

    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "A", "type": "function"}, {"name": "B", "type": "function"}],
        edges_data=[{"source": "A", "target": "B", "edge_type": "calls",
                     "source_type": "function", "target_type": "function"}],
    )
    gs.replace_file_entity_map(em, ROOT, "/sole.py")

    a_id = entity_id("A", "function", ROOT)
    b_id = entity_id("B", "function", ROOT)
    e_id = edge_id(a_id, b_id, "calls", ROOT)

    db_path = gs._db_path(ROOT)

    # Manually insert a sentinel contribution (simulates old-format migration data)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT OR IGNORE INTO edge_contributions (root_id, file_path, edge_id, source_id, target_id, edge_type, weight, description) VALUES (?,?,?,?,?,?,?,?)",
        (ROOT, MIGRATION_SENTINEL_FILE, e_id, a_id, b_id, "calls", 0.5, ""),
    )
    conn.commit()
    conn.close()

    # Delete the sole file → both A and B become delete_ids
    gs.delete_file_entities("/sole.py", ROOT)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sentinel_left = conn.execute(
        "SELECT COUNT(*) FROM edge_contributions WHERE root_id=? AND file_path=?",
        (ROOT, MIGRATION_SENTINEL_FILE),
    ).fetchone()[0]
    conn.close()

    assert sentinel_left == 0, (
        f"{sentinel_left} sentinel contribution(s) remain after entity delete — phantom sentinel regression"
    )


# ---------------------------------------------------------------------------
# Phase 3-Pre blocker regression tests (B1, B4, B5)
# ---------------------------------------------------------------------------


def _make_entity_map_with_chunk_ids(entities_data, edges_data):
    """Like _make_entity_map but uses chunk_ids (plural list) on entities."""

    def _make_entity(d):
        e = types.SimpleNamespace()
        e.name = d["name"]
        e.type = d["type"]
        e.description = d.get("description", "")
        e.chunk_ids = d.get("chunk_ids", [])
        return e

    def _make_edge(d):
        ed = types.SimpleNamespace()
        ed.source = d["source"]
        ed.target = d["target"]
        ed.source_type = d.get("source_type", "unknown")
        ed.target_type = d.get("target_type", "unknown")
        ed.edge_type = d["edge_type"]
        ed.weight = d.get("weight", 1.0)
        ed.description = d.get("description", "")
        return ed

    em = types.SimpleNamespace()
    em.entities = [_make_entity(e) for e in entities_data]
    em.edges = [_make_edge(e) for e in edges_data]
    return em


def test_entity_chunks_populated_on_replace(tmp_path):
    """B1/B4 — entity_chunks rows are written for each chunk_id in the entity map."""
    import sqlite3 as _sqlite3
    gs = make_store(tmp_path)

    em = _make_entity_map_with_chunk_ids(
        entities_data=[
            {"name": "Foo", "type": "function", "chunk_ids": [0, 2]},
            {"name": "Bar", "type": "class", "chunk_ids": [1]},
        ],
        edges_data=[],
    )
    gs.replace_file_entity_map(em, ROOT, "/file.py")

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT chunk_id FROM entity_chunks WHERE root_id=? AND file_path=? ORDER BY chunk_id",
        (ROOT, "/file.py"),
    ).fetchall()
    conn.close()

    chunk_ids_found = {r[0] for r in rows}
    assert chunk_ids_found == {0, 1, 2}, f"Expected {{0,1,2}} but got {chunk_ids_found}"


def test_entity_chunks_cleared_on_re_index(tmp_path):
    """B1 — entity_chunks are cleaned up when a file is re-indexed; no stale rows accumulate."""
    import sqlite3 as _sqlite3
    gs = make_store(tmp_path)

    # First index: entity with chunk_ids [0, 1, 2]
    em1 = _make_entity_map_with_chunk_ids(
        entities_data=[{"name": "Alpha", "type": "function", "chunk_ids": [0, 1, 2]}],
        edges_data=[],
    )
    gs.replace_file_entity_map(em1, ROOT, "/a.py")

    # Second index: same entity but only chunk_id [0]
    em2 = _make_entity_map_with_chunk_ids(
        entities_data=[{"name": "Alpha", "type": "function", "chunk_ids": [0]}],
        edges_data=[],
    )
    gs.replace_file_entity_map(em2, ROOT, "/a.py")

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT chunk_id FROM entity_chunks WHERE root_id=? AND file_path='/a.py'",
        (ROOT,),
    ).fetchall()
    conn.close()

    chunk_ids_found = {r[0] for r in rows}
    assert chunk_ids_found == {0}, f"Stale entity_chunks after re-index: {chunk_ids_found}"


def test_entity_chunks_deleted_with_file(tmp_path):
    """B1 — delete_file_entities removes entity_chunks rows for the file."""
    import sqlite3 as _sqlite3
    gs = make_store(tmp_path)

    em = _make_entity_map_with_chunk_ids(
        entities_data=[{"name": "Qux", "type": "concept", "chunk_ids": [0]}],
        edges_data=[],
    )
    gs.replace_file_entity_map(em, ROOT, "/del.py")

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    before = conn.execute(
        "SELECT COUNT(*) FROM entity_chunks WHERE root_id=? AND file_path=?",
        (ROOT, "/del.py"),
    ).fetchone()[0]
    conn.close()
    assert before > 0, "entity_chunks should be non-empty after indexing"

    gs.delete_file_entities("/del.py", ROOT)

    conn = _sqlite3.connect(db_path)
    after = conn.execute(
        "SELECT COUNT(*) FROM entity_chunks WHERE root_id=? AND file_path=?",
        (ROOT, "/del.py"),
    ).fetchone()[0]
    conn.close()
    assert after == 0, "entity_chunks not cleaned after delete_file_entities"


def test_write_lock_exists(tmp_path):
    """B5 — GraphStore has a threading.Lock protecting its write path."""
    import threading
    gs = make_store(tmp_path)
    assert hasattr(gs, "_write_lock"), "GraphStore missing _write_lock attribute"
    assert isinstance(gs._write_lock, type(threading.Lock())), "_write_lock is not a threading.Lock"


def test_empty_communities_publish(tmp_path):
    """B3 — replace_communities_if_current accepts an empty communities list."""
    gs = make_store(tmp_path)

    gs.mark_communities_dirty(ROOT)
    v = gs.get_graph_version(ROOT)

    ok = gs.replace_communities_if_current(ROOT, v, "empty_build", communities=[])
    assert ok is True, "Should be able to publish an empty community set"
    assert not gs.are_communities_dirty(ROOT), "Root should be clean after empty publication"


def test_delete_file_uses_purge_not_raw_delete(tmp_path):
    """B1 — delete_file_entities cleans entity_chunks through _purge_file_contributions.

    Two files share entity E via edge; deleting file A must leave E's entity_chunks
    for file B intact.
    """
    import sqlite3 as _sqlite3
    gs = make_store(tmp_path)

    # File A contributes entity E with chunk_id 0
    emA = _make_entity_map_with_chunk_ids(
        entities_data=[{"name": "E", "type": "function", "chunk_ids": [0]}],
        edges_data=[],
    )
    gs.replace_file_entity_map(emA, ROOT, "/a.py")

    # File B also references entity E with chunk_id 1
    emB = _make_entity_map_with_chunk_ids(
        entities_data=[{"name": "E", "type": "function", "chunk_ids": [1]}],
        edges_data=[],
    )
    gs.replace_file_entity_map(emB, ROOT, "/b.py")

    # Delete file A — entity E remains because B still references it
    gs.delete_file_entities("/a.py", ROOT)

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    chunks_for_b = conn.execute(
        "SELECT chunk_id FROM entity_chunks WHERE root_id=? AND file_path='/b.py'",
        (ROOT,),
    ).fetchall()
    entity_count = conn.execute(
        "SELECT COUNT(*) FROM entities WHERE root_id=?", (ROOT,)
    ).fetchone()[0]
    chunks_for_a = conn.execute(
        "SELECT COUNT(*) FROM entity_chunks WHERE root_id=? AND file_path='/a.py'",
        (ROOT,),
    ).fetchone()[0]
    conn.close()

    assert {r[0] for r in chunks_for_b} == {1}, "B's entity_chunks should survive A's deletion"
    assert entity_count == 1, "Entity E should still exist (referenced by B)"
    assert chunks_for_a == 0, "A's entity_chunks should be gone"


# ---------------------------------------------------------------------------
# Regression: Fix 1 — frequency underflow on re-index
# ---------------------------------------------------------------------------

def test_frequency_preserved_on_reindex(tmp_path):
    """Fix 1 — Re-indexing a file that declares a shared entity must not decrement its frequency.

    Scenario: entity E declared by both A and B (frequency=2).  Re-index A → frequency stays 2.
    Prior to the fix, _purge_file_contributions decremented frequency but replace_file_entity_map
    UPDATE branch never re-incremented it, so frequency would drop to 1.
    """
    import sqlite3 as _sqlite3

    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "E", "type": "function"}],
        edges_data=[],
    )
    gs.replace_file_entity_map(em, ROOT, "/a.py")
    gs.replace_file_entity_map(em, ROOT, "/b.py")

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    from vectors.graph_store import entity_id
    eid = entity_id("E", "function", ROOT)
    freq_before = conn.execute("SELECT frequency FROM entities WHERE id=?", (eid,)).fetchone()[0]
    conn.close()
    assert freq_before == 2, f"Expected frequency=2 after indexing two files, got {freq_before}"

    # Re-index file A with the same entity
    gs.replace_file_entity_map(em, ROOT, "/a.py")

    conn = _sqlite3.connect(db_path)
    freq_after = conn.execute("SELECT frequency FROM entities WHERE id=?", (eid,)).fetchone()[0]
    fp_after = conn.execute("SELECT file_paths FROM entities WHERE id=?", (eid,)).fetchone()[0]
    conn.close()

    assert freq_after == 2, (
        f"Frequency underflow: expected 2 after re-index, got {freq_after}"
    )
    assert "/a.py" in fp_after and "/b.py" in fp_after, (
        f"Both files should still be in file_paths after re-index, got {fp_after}"
    )


# ---------------------------------------------------------------------------
# Regression: Fix 2 — orphan edges when entity deleted
# ---------------------------------------------------------------------------

def test_no_orphan_edges_after_entity_deletion(tmp_path):
    """Fix 2 — Deleting entity E (sole source file A) must also remove cross-file contributions.

    Scenario:
    - File A declares entity E.
    - File B has an edge X→E (E already exists, so no stub; B's edge_contribution references E).
    - Re-index file A with NO entity E.
    - After re-index, E is deleted and B's contribution to X→E must be purged too.
    - materialized edges must be empty (no orphan edge X→deleted_E).
    """
    import sqlite3 as _sqlite3

    gs = make_store(tmp_path)

    em_a = _make_entity_map(
        entities_data=[{"name": "E", "type": "function"}],
        edges_data=[],
    )
    em_b = _make_entity_map(
        entities_data=[{"name": "X", "type": "function"}],
        edges_data=[{"source": "X", "target": "E", "edge_type": "calls",
                     "source_type": "function", "target_type": "function"}],
    )
    gs.replace_file_entity_map(em_a, ROOT, "/a.py")
    gs.replace_file_entity_map(em_b, ROOT, "/b.py")

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    edges_before = conn.execute("SELECT COUNT(*) FROM edges WHERE root_id=?", (ROOT,)).fetchone()[0]
    conn.close()
    assert edges_before == 1, f"Edge X→E should exist before re-index, got {edges_before}"

    # Re-index A with an empty entity_map (E is no longer declared by A)
    em_a_empty = _make_entity_map(entities_data=[], edges_data=[])
    gs.replace_file_entity_map(em_a_empty, ROOT, "/a.py")

    conn = _sqlite3.connect(db_path)
    edges_after = conn.execute("SELECT COUNT(*) FROM edges WHERE root_id=?", (ROOT,)).fetchone()[0]
    orphan_contribs = conn.execute(
        """
        SELECT COUNT(*) FROM edge_contributions ec
        WHERE ec.root_id=?
          AND NOT EXISTS (SELECT 1 FROM entities WHERE id=ec.source_id AND root_id=?)
          AND NOT EXISTS (SELECT 1 FROM entities WHERE id=ec.target_id AND root_id=?)
        """,
        (ROOT, ROOT, ROOT),
    ).fetchone()[0]
    conn.close()

    assert edges_after == 0, (
        f"Orphan edge regression: {edges_after} edge(s) remain after E was deleted"
    )
    assert orphan_contribs == 0, (
        f"{orphan_contribs} orphan contribution(s) with missing endpoints remain"
    )


# ---------------------------------------------------------------------------
# Regression: Fix 6 — delete_file_entities resets communities_version=0
# ---------------------------------------------------------------------------

def test_delete_file_entities_resets_communities_version(tmp_path):
    """Fix 6 — delete_file_entities must set communities_version=0 in meta.

    This keeps communities_version in sync with graph_version (both paths that
    invalidate committed communities should zero communities_version).
    """
    import sqlite3 as _sqlite3

    gs = make_store(tmp_path)

    em = _make_entity_map(
        entities_data=[{"name": "Z", "type": "function"}],
        edges_data=[],
    )
    gs.replace_file_entity_map(em, ROOT, "/z.py")
    v = gs.get_graph_version(ROOT)

    # Simulate a committed generation
    gs.replace_communities_if_current(ROOT, v, "build_xyz", communities=[])
    cv_before, bid_before = gs.get_committed_generation(ROOT)
    assert cv_before == v, "communities_version should equal graph_version after publication"

    # Now delete the file — must reset communities_version=0
    gs.delete_file_entities("/z.py", ROOT)

    db_path = gs._db_path(ROOT)
    conn = _sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT graph_version, communities_version, committed_build_id FROM meta WHERE root_id=?",
        (ROOT,),
    ).fetchone()
    conn.close()

    gv, cv, bid = row
    assert cv == 0, f"communities_version should be reset to 0 after delete_file_entities, got {cv}"
    assert bid is None, "committed_build_id should be NULL after delete_file_entities"
    assert gv > v, "graph_version should have incremented"


# ---------------------------------------------------------------------------
# entity_community join table (ADR-0009–0021, Seam 1)
# ---------------------------------------------------------------------------


def test_entity_community_upsert_and_lookup(tmp_path):
    """upsert_entity_community_rows stores rows; get_community_ids_for_entities returns them."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)

    gs.upsert_entity_community_rows(ROOT, "build-1", [("e1", "c1"), ("e1", "c2"), ("e2", "c3")])
    result = gs.get_community_ids_for_entities(ROOT, ["e1"])
    assert result == {"c1", "c2"}

    result2 = gs.get_community_ids_for_entities(ROOT, ["e2"])
    assert result2 == {"c3"}

    result3 = gs.get_community_ids_for_entities(ROOT, ["e1", "e2"])
    assert result3 == {"c1", "c2", "c3"}


def test_entity_community_upsert_idempotent(tmp_path):
    """Repeated upserts of the same rows must not raise or duplicate."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)

    rows = [("e1", "c1"), ("e2", "c2")]
    gs.upsert_entity_community_rows(ROOT, "build-1", rows)
    gs.upsert_entity_community_rows(ROOT, "build-1", rows)  # no-op via INSERT OR IGNORE

    result = gs.get_community_ids_for_entities(ROOT, ["e1", "e2"])
    assert result == {"c1", "c2"}


def test_entity_community_stale_deletion(tmp_path):
    """delete_entity_community_stale removes old build rows, keeps current."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)

    gs.upsert_entity_community_rows(ROOT, "build-old", [("e1", "c_old")])
    gs.upsert_entity_community_rows(ROOT, "build-new", [("e1", "c_new")])

    gs.delete_entity_community_stale(ROOT, "build-new")

    result = gs.get_community_ids_for_entities(ROOT, ["e1"])
    assert "c_new" in result
    assert "c_old" not in result


def test_entity_community_empty_lookup(tmp_path):
    """get_community_ids_for_entities returns empty set for unknown entity."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)

    result = gs.get_community_ids_for_entities(ROOT, ["nonexistent"])
    assert result == set()

    result2 = gs.get_community_ids_for_entities(ROOT, [])
    assert result2 == set()


def test_get_committed_community_ids(tmp_path):
    """get_committed_community_ids returns ids matching the build."""
    gs = make_store(tmp_path)
    gs._ensure_schema(ROOT)

    # Insert communities directly via replace_communities_if_current
    em = _make_entity_map(
        entities_data=[{"name": "A", "type": "func"}],
        edges_data=[],
    )
    gs.replace_file_entity_map(em, ROOT, "/a.py")
    v = gs.get_graph_version(ROOT)

    communities = [
        {"community_id": "c1", "level": 0, "parent_id": None, "entity_ids": "[]",
         "file_ids": "[]", "summary": "s1", "report": None},
        {"community_id": "c2", "level": 0, "parent_id": None, "entity_ids": "[]",
         "file_ids": "[]", "summary": "s2", "report": None},
    ]
    gs.replace_communities_if_current(ROOT, v, "build-xyz", communities=communities)

    ids = gs.get_committed_community_ids(ROOT, "build-xyz")
    assert set(ids) == {"c1", "c2"}

    ids_other = gs.get_committed_community_ids(ROOT, "build-other")
    assert ids_other == []
