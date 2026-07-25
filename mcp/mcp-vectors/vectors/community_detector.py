"""
Community detection for GraphRAG.

Tries graspologic_native (hierarchical Leiden) first, falls back to
NetworkX greedy_modularity_communities (flat, level=0).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class DetectorUnavailableError(Exception):
    """Raised when neither community detection backend is available."""
    pass


@dataclass(frozen=True)
class CommunityCandidate:
    community_id: str
    level: int
    parent_id: str | None
    entity_ids: tuple[str, ...]  # sorted
    file_ids: tuple[str, ...]    # sorted


# (communities sorted by (level, community_id), algorithm_name)
DetectionResult = tuple[tuple[CommunityCandidate, ...], str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_file_paths(entity: dict) -> list[str]:
    """Extract file_paths list from entity dict, handling JSON string format."""
    fps = entity.get("file_paths", [])
    if isinstance(fps, str):
        try:
            fps = json.loads(fps)
        except (json.JSONDecodeError, ValueError):
            fps = []
    return fps if fps else []


def _project_to_undirected(snapshot):
    """Project directed snapshot to undirected weighted graph."""
    import networkx as nx  # lazy; raises ImportError if not installed

    g = nx.Graph()

    # Add all entities as nodes
    for e in snapshot.entities:
        g.add_node(e["id"], name=e["name"], type=e["type"], degree=e["degree"])

    # Aggregate edges by unordered endpoint pair
    edge_map: dict = {}  # (min_id, max_id) -> (weight_sum, descriptions)
    for edge in snapshot.edges:
        src, tgt = edge["source_id"], edge["target_id"]
        key = (min(src, tgt), max(src, tgt))
        if key not in edge_map:
            edge_map[key] = (0.0, [])
        weight, descs = edge_map[key]
        edge_map[key] = (weight + edge["weight"], descs + [edge["description"]])

    # Add aggregated edges; exclude self-loops
    for (u, v), (weight, descs) in edge_map.items():
        if u != v:
            g.add_edge(u, v, weight=weight, description="; ".join(filter(None, descs)))

    # Retain isolates (nodes with degree 0) — already present via add_node above
    return g


def _detect_graspologic(g, snapshot) -> DetectionResult | None:
    """
    Use graspologic_native hierarchical Leiden.

    Returns None to signal fallback on import failure or runtime error.
    """
    try:
        from graspologic_native import hierarchical_leiden
    except ImportError:
        return None  # Signal to fallback

    try:
        # hierarchical_leiden returns {level: {community_id: set(node_ids)}}
        hierarchy = hierarchical_leiden(g, seed=42)  # Fixed seed for determinism

        # First pass: generate deterministic SHA-256 community IDs for every
        # (level, graspologic_community_id) pair, keyed for parent lookup.
        sha_id_map: dict[tuple[int, object], str] = {}
        for level in sorted(hierarchy.keys()):
            for grasp_cid, entity_ids in hierarchy[level].items():
                sorted_eids = tuple(sorted(entity_ids))
                sha_id = hashlib.sha256(
                    f"{snapshot.root_id}|{sorted_eids}".encode()
                ).hexdigest()
                sha_id_map[(level, grasp_cid)] = sha_id

        # Second pass: build CommunityCandidate objects with correct parent SHA IDs.
        communities: list[CommunityCandidate] = []
        for level in sorted(hierarchy.keys()):
            for grasp_cid, entity_ids in hierarchy[level].items():
                parent_sha_id: str | None = None

                if level > 0:
                    # Find the unique parent: level-(k-1) community that contains
                    # every entity in this community.
                    for parent_grasp_cid, parent_eids in hierarchy[level - 1].items():
                        if all(eid in parent_eids for eid in entity_ids):
                            if parent_sha_id is not None:
                                logger.warning(
                                    "Hierarchy violation at level %d community %s: "
                                    "multiple parents. Falling back to NetworkX.",
                                    level, grasp_cid,
                                )
                                return None
                            parent_sha_id = sha_id_map[(level - 1, parent_grasp_cid)]
                    if parent_sha_id is None:
                        logger.warning(
                            "Hierarchy violation at level %d community %s: "
                            "no parent found. Falling back to NetworkX.",
                            level, grasp_cid,
                        )
                        return None

                sorted_eids = tuple(sorted(entity_ids))
                cid = sha_id_map[(level, grasp_cid)]

                file_ids: set[str] = set()
                for eid in entity_ids:
                    for entity in snapshot.entities:
                        if entity["id"] == eid:
                            for fp in _get_file_paths(entity):
                                if fp:  # Skip empty sentinel file_path
                                    file_ids.add(fp)

                communities.append(CommunityCandidate(
                    community_id=cid,
                    level=level,
                    parent_id=parent_sha_id,
                    entity_ids=sorted_eids,
                    file_ids=tuple(sorted(file_ids)),
                ))

        communities.sort(key=lambda c: (c.level, c.community_id))
        return (tuple(communities), "graspologic_native")

    except Exception as e:
        logger.warning("graspologic_native failed: %s. Falling back to NetworkX.", e)
        return None


def _detect_networkx(g, snapshot) -> DetectionResult:
    """Use NetworkX greedy_modularity_communities (flat, level=0)."""
    try:
        import networkx as nx
    except ImportError:
        raise DetectorUnavailableError("NetworkX is not available")

    try:
        # greedy_modularity_communities returns an iterator of frozensets
        communities_raw = list(nx.community.greedy_modularity_communities(g))

        candidates: list[CommunityCandidate] = []
        for entity_ids in communities_raw:
            sorted_eids = tuple(sorted(entity_ids))
            cid = hashlib.sha256(
                f"{snapshot.root_id}|{sorted_eids}".encode()
            ).hexdigest()

            file_ids: set[str] = set()
            for eid in entity_ids:
                for entity in snapshot.entities:
                    if entity["id"] == eid:
                        for fp in _get_file_paths(entity):
                            if fp:
                                file_ids.add(fp)

            candidates.append(CommunityCandidate(
                community_id=cid,
                level=0,
                parent_id=None,
                entity_ids=sorted_eids,
                file_ids=tuple(sorted(file_ids)),
            ))

        candidates.sort(key=lambda c: (c.level, c.community_id))
        return (tuple(candidates), "networkx")

    except Exception as e:
        logger.error("NetworkX detection failed: %s", e)
        raise DetectorUnavailableError(f"Community detection failed: {e}")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def detect_communities(snapshot) -> DetectionResult:
    """
    Detect hierarchical communities from a graph snapshot.

    Returns:
        (tuple of CommunityCandidate sorted by (level, community_id), algorithm_name)

    Raises:
        DetectorUnavailableError if neither backend is available
    """
    if not snapshot.entities or not snapshot.edges:
        # Empty / edge-less graph: each entity becomes its own singleton community.
        candidates: list[CommunityCandidate] = []
        for entity in snapshot.entities:
            cid = hashlib.sha256(
                f"{snapshot.root_id}|{entity['id']}".encode()
            ).hexdigest()
            file_ids = tuple(sorted(f for f in _get_file_paths(entity) if f))
            candidates.append(CommunityCandidate(
                community_id=cid,
                level=0,
                parent_id=None,
                entity_ids=(entity["id"],),
                file_ids=file_ids,
            ))
        candidates.sort(key=lambda c: (c.level, c.community_id))
        return (tuple(candidates), "singleton")

    # Check backend availability before projecting the graph.
    _graspologic_ok = False
    _networkx_ok = False
    try:
        import graspologic_native  # noqa: F401
        _graspologic_ok = True
    except ImportError:
        pass
    try:
        import networkx  # noqa: F401
        _networkx_ok = True
    except ImportError:
        pass

    if not _graspologic_ok and not _networkx_ok:
        raise DetectorUnavailableError(
            "Neither graspologic-native nor NetworkX is available for community detection"
        )

    # Project to undirected graph (requires networkx for nx.Graph representation).
    g = _project_to_undirected(snapshot)

    # Try graspologic first.
    result = _detect_graspologic(g, snapshot)
    if result is not None:
        return result

    # Fallback to NetworkX.
    return _detect_networkx(g, snapshot)
