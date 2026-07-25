"""
Tests for vectors.community_detector.

Strategy
--------
* Tests that only exercise the singleton path (no edges) never import networkx.
* Tests that exercise graph-detection code paths inject a minimal mock networkx
  module via sys.modules so the suite passes whether or not networkx is installed.
* graspologic_native-specific tests are skipped when the package is absent.
"""
from __future__ import annotations

import hashlib
import sys
import types
from unittest.mock import patch

import pytest

from vectors.graph_store import GraphSnapshot
from vectors.community_detector import (
    CommunityCandidate,
    DetectorUnavailableError,
    detect_communities,
)

# ---------------------------------------------------------------------------
# Optional backend detection
# ---------------------------------------------------------------------------

HAS_GRASPOLOGIC = False
try:
    import graspologic_native  # noqa: F401
    HAS_GRASPOLOGIC = True
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

ROOT = "test_root_abc"


def _entity(eid: str, name: str = "", file_paths=None, degree: int = 0) -> dict:
    return {
        "id": eid,
        "name": name or eid,
        "type": "class",
        "degree": degree,
        "file_paths": file_paths or [],
    }


def _edge(src: str, tgt: str, weight: float = 1.0, desc: str = "") -> dict:
    return {
        "source_id": src,
        "target_id": tgt,
        "weight": weight,
        "description": desc,
    }


def _snapshot(entities, edges=()) -> GraphSnapshot:
    return GraphSnapshot(
        root_id=ROOT,
        graph_version=1,
        entities=tuple(entities),
        edges=tuple(edges),
    )


# ---------------------------------------------------------------------------
# Minimal networkx mock (used only when testing graph-detection code paths)
# ---------------------------------------------------------------------------

class _MockGraph:
    """Bare-bones undirected graph that satisfies _project_to_undirected."""

    def __init__(self):
        self._nodes: dict = {}
        self._adj: dict = {}

    def add_node(self, n, **attrs):
        self._nodes[n] = attrs
        self._adj.setdefault(n, {})

    def add_edge(self, u, v, **attrs):
        self._adj.setdefault(u, {})[v] = attrs
        self._adj.setdefault(v, {})[u] = attrs

    @property
    def nodes(self):
        return self._nodes


def _make_mock_nx(communities: list[frozenset]):
    """Return a minimal networkx-shaped module whose community detection
    returns the given community frozensets."""
    community_mod = types.SimpleNamespace(
        greedy_modularity_communities=lambda g, seed=None: communities
    )
    return types.SimpleNamespace(
        Graph=_MockGraph,
        community=community_mod,
    )


# ---------------------------------------------------------------------------
# 1. Empty graph → singleton communities
# ---------------------------------------------------------------------------

def test_empty_graph_singleton_communities():
    """Snapshot with 0 edges: every entity becomes its own level-0 community."""
    entities = [_entity("e1"), _entity("e2"), _entity("e3")]
    snap = _snapshot(entities)
    communities, algo = detect_communities(snap)

    assert algo == "singleton"
    assert len(communities) == 3
    for c in communities:
        assert c.level == 0
        assert len(c.entity_ids) == 1
        assert c.parent_id is None
    # Each community contains exactly one of the entity IDs
    assigned = {c.entity_ids[0] for c in communities}
    assert assigned == {"e1", "e2", "e3"}


# ---------------------------------------------------------------------------
# 2. Deterministic community IDs
# ---------------------------------------------------------------------------

def test_deterministic_community_ids():
    """Running detector twice on same snapshot produces identical IDs and ordering."""
    entities = [_entity("e1"), _entity("e2"), _entity("e3")]
    snap = _snapshot(entities)

    result1, algo1 = detect_communities(snap)
    result2, algo2 = detect_communities(snap)

    assert algo1 == algo2
    assert len(result1) == len(result2)
    for c1, c2 in zip(result1, result2):
        assert c1.community_id == c2.community_id
        assert c1.entity_ids == c2.entity_ids
        assert c1.file_ids == c2.file_ids


# ---------------------------------------------------------------------------
# 3. NetworkX fallback returns flat communities (all level 0)
# ---------------------------------------------------------------------------

def test_networkx_fallback_returns_flat():
    """Force graspologic unavailable; detector falls back to networkx and
    returns only level-0 communities."""
    entities = [
        _entity("e1", degree=1),
        _entity("e2", degree=1),
        _entity("e3", degree=1),
    ]
    edges = [_edge("e1", "e2"), _edge("e2", "e3")]
    snap = _snapshot(entities, edges)

    mock_nx = _make_mock_nx([frozenset(["e1", "e2"]), frozenset(["e3"])])

    with patch.dict(sys.modules, {
        "graspologic_native": None,
        "networkx": mock_nx,
    }):
        communities, algo = detect_communities(snap)

    assert algo == "networkx"
    assert len(communities) > 0
    assert all(c.level == 0 for c in communities)
    assert all(c.parent_id is None for c in communities)


# ---------------------------------------------------------------------------
# 4. graspologic hierarchy when available
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_GRASPOLOGIC, reason="graspologic_native not installed")
def test_graspologic_hierarchy_when_available():
    """When graspologic is importable, at least some communities may have level > 0."""
    # Build a moderately connected graph so hierarchical Leiden can find structure.
    entity_ids = [f"e{i}" for i in range(8)]
    entities = [_entity(eid, degree=2) for eid in entity_ids]
    edge_pairs = [
        ("e0", "e1"), ("e1", "e2"), ("e2", "e3"),
        ("e4", "e5"), ("e5", "e6"), ("e6", "e7"),
        ("e3", "e4"),
    ]
    edges = [_edge(s, t) for s, t in edge_pairs]
    snap = _snapshot(entities, edges)

    communities, algo = detect_communities(snap)

    assert algo == "graspologic_native"
    assert len(communities) > 0
    # All assigned entity IDs are a subset of the snapshot's entity IDs
    all_eids = {eid for c in communities for eid in c.entity_ids}
    assert all_eids <= set(entity_ids)


# ---------------------------------------------------------------------------
# 5. DetectorUnavailableError when both backends missing
# ---------------------------------------------------------------------------

def test_detector_unavailable_error_when_both_missing():
    """Both imports fail → DetectorUnavailableError is raised."""
    entities = [_entity("e1", degree=1), _entity("e2", degree=1)]
    edges = [_edge("e1", "e2")]
    snap = _snapshot(entities, edges)

    with patch.dict(sys.modules, {"graspologic_native": None, "networkx": None}):
        with pytest.raises(DetectorUnavailableError):
            detect_communities(snap)


# ---------------------------------------------------------------------------
# 6. Isolate entities form singleton communities
# ---------------------------------------------------------------------------

def test_isolate_entities_form_singleton_communities():
    """Entities with no edges (isolates) each become their own level-0 community."""
    entities = [_entity("a", degree=0), _entity("b", degree=0)]
    snap = _snapshot(entities)  # no edges

    communities, algo = detect_communities(snap)

    assert algo == "singleton"
    assert len(communities) == 2
    for c in communities:
        assert c.level == 0
        assert c.parent_id is None
        assert len(c.entity_ids) == 1


# ---------------------------------------------------------------------------
# 7. Output is always sorted by (level, community_id)
# ---------------------------------------------------------------------------

def test_communities_sorted_by_level_then_id():
    """detect_communities always returns candidates sorted by (level, community_id)."""
    entities = [_entity(f"node{i}") for i in range(6)]
    snap = _snapshot(entities)  # no edges → singleton path

    communities, _ = detect_communities(snap)

    for i in range(len(communities) - 1):
        key_a = (communities[i].level, communities[i].community_id)
        key_b = (communities[i + 1].level, communities[i + 1].community_id)
        assert key_a <= key_b, f"Order violated: {key_a} > {key_b}"


# ---------------------------------------------------------------------------
# 8. Hierarchy containment (graspologic only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not HAS_GRASPOLOGIC, reason="graspologic_native not installed")
def test_hierarchy_containment():
    """Every level-k community is the child of exactly one level-(k-1) community,
    i.e., parent_id refers to a community that exists at level k-1."""
    entity_ids = [f"n{i}" for i in range(10)]
    entities = [_entity(eid, degree=2) for eid in entity_ids]
    edges = [_edge(f"n{i}", f"n{(i+1) % 10}") for i in range(10)]
    snap = _snapshot(entities, edges)

    communities, algo = detect_communities(snap)

    # Only verify containment when graspologic was actually used.
    if algo != "graspologic_native":
        pytest.skip("graspologic fell back to networkx; hierarchy test N/A")

    by_level: dict[int, list[CommunityCandidate]] = {}
    for c in communities:
        by_level.setdefault(c.level, []).append(c)

    max_level = max(by_level) if by_level else 0
    for level in range(1, max_level + 1):
        parent_ids = {p.community_id for p in by_level.get(level - 1, [])}
        for c in by_level.get(level, []):
            if c.parent_id is not None:
                assert c.parent_id in parent_ids, (
                    f"Community {c.community_id} at level {level} has parent_id "
                    f"{c.parent_id} which is not in level-{level-1} community IDs."
                )


# ---------------------------------------------------------------------------
# 9. file_ids populated from entity file_paths
# ---------------------------------------------------------------------------

def test_file_ids_populated_from_entity_paths():
    """Entity with file_paths=['/a.py', '/b.py'] in a singleton community has
    both paths in community.file_ids."""
    entities = [
        _entity("e1", file_paths=["/a.py", "/b.py"]),
    ]
    snap = _snapshot(entities)  # no edges → singleton path

    communities, algo = detect_communities(snap)

    assert algo == "singleton"
    assert len(communities) == 1
    c = communities[0]
    assert "/a.py" in c.file_ids
    assert "/b.py" in c.file_ids


# ---------------------------------------------------------------------------
# Bonus: file_ids skips the empty-sentinel path
# ---------------------------------------------------------------------------

def test_file_ids_skip_sentinel():
    """Empty-string file_path (migration sentinel) is excluded from file_ids."""
    entities = [
        _entity("e1", file_paths=["", "/real.py"]),
    ]
    snap = _snapshot(entities)

    communities, _ = detect_communities(snap)

    assert len(communities) == 1
    assert "" not in communities[0].file_ids
    assert "/real.py" in communities[0].file_ids


# ---------------------------------------------------------------------------
# Bonus: JSON-encoded file_paths (as stored in SQLite) are parsed correctly
# ---------------------------------------------------------------------------

def test_file_ids_from_json_encoded_file_paths():
    """When file_paths is a JSON string (as returned by read_graph_snapshot),
    it is decoded and used correctly."""
    import json

    entities = [
        {
            "id": "e1",
            "name": "Entity1",
            "type": "class",
            "degree": 0,
            "file_paths": json.dumps(["/src/foo.py", "/src/bar.py"]),
        }
    ]
    snap = _snapshot(entities)

    communities, _ = detect_communities(snap)

    assert len(communities) == 1
    assert "/src/foo.py" in communities[0].file_ids
    assert "/src/bar.py" in communities[0].file_ids


# ---------------------------------------------------------------------------
# Bonus: networkx fallback with community containing file_paths
# ---------------------------------------------------------------------------

def test_networkx_fallback_file_ids():
    """In networkx fallback mode, file_ids are collected from entity file_paths."""
    entities = [
        _entity("e1", file_paths=["/x.py"], degree=1),
        _entity("e2", file_paths=["/y.py"], degree=1),
    ]
    edges = [_edge("e1", "e2")]
    snap = _snapshot(entities, edges)

    # Mock networkx: put both entities in one community
    mock_nx = _make_mock_nx([frozenset(["e1", "e2"])])

    with patch.dict(sys.modules, {
        "graspologic_native": None,
        "networkx": mock_nx,
    }):
        communities, algo = detect_communities(snap)

    assert algo == "networkx"
    assert len(communities) == 1
    c = communities[0]
    assert "/x.py" in c.file_ids
    assert "/y.py" in c.file_ids
