# Route graph-query tools through a single pipeline seam

## Status

proposed

## Context

The three graph-query MCP tools — `get_entity_callers`, `get_entity_neighbors`, `search_entities` in `server.py` — each construct a fresh `GraphStore(db_dir=GRAPH_DB_DIR)` and repeat the `has_root` guard inline. Meanwhile the pipeline already holds an initialized `_graph_store`, and the community tools (`list_communities`, `get_community_report`) correctly go through it. This is two independent adapters at the same seam: the direct-construction path in `server.py` cannot see the pipeline's in-memory state (dirty flags, claimed leases). The three graph tools also skip `increment_operations()` / `decrement_operations()`, unlike every other read tool.

## Decision

Add three delegating methods to `RAGPipeline`: `find_entities(root_path, query, limit)`, `get_neighbors(root_path, entity_name, max_depth, edge_types)`, and `get_callers(root_path, entity_name)`. Each resolves the `root_id`, applies the `has_root` guard, delegates to the pipeline's `_graph_store`, and participates in shutdown coordination via the operation guard. The three `server.py` tools call these pipeline methods instead of constructing their own `GraphStore`. One seam, one adapter.

Graph reads are treated as operations for graceful-shutdown purposes — `get_entity_neighbors` with `max_depth=5` can traverse large subgraphs, so exempting read-only tools would be inconsistent with `list_communities`.

## Considered Options

- **Extract a separate `GraphQueryService` class.** Rejected for now: architecturally cleaner but adds a layer when the three methods are genuinely thin wrappers over `_graph_store`. Revisit if the pipeline interface grows further.
- **Also fold `list_communities` / `get_community_report` into the new methods.** Rejected: those tools carry extra logic (dirty-check, auto-rebuild trigger) that does not belong in `find_entities`; the DRY payoff is modest.
- **Leave graph tools out of shutdown coordination.** Rejected: read-only does not mean cheap, and consistency with other read tools matters.

## Consequences

- Graph access flows through one object; dirty-flag and lease state stay coherent.
- The direct `GraphStore(db_dir=GRAPH_DB_DIR)` construction disappears from `server.py`.
- Graph tools now reject calls during shutdown, closing a pre-existing inconsistency.
