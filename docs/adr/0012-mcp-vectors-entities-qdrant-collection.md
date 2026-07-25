# Dedicated Qdrant Collection for Entity Embeddings

## Context

ADR-0009 establishes that entity embeddings are stored in Qdrant to enable semantic entity search at `search_global` time. Two existing collections already exist: `mcp_vectors` (chunk embeddings) and `mcp_vectors_communities` (community report embeddings). A decision is needed on whether entity embeddings share a collection with an existing store or occupy their own.

Entities have a distinct lifecycle from chunks and communities:
- Written during extraction (background, per-file)
- Keyed by `(root_id, entity_id)` — stable across detection builds
- Cleaned up when a file is removed from the index (entity deleted from graph store)
- Toggled off entirely when `ENTITY_EXTRACTION=false`

## Decision

Store entity embeddings in a new dedicated Qdrant collection `mcp_vectors_entities`, managed by a new `QdrantEntities` class that mirrors the `QdrantCommunities` pattern. Each entity point carries the payload fields: `entity_id`, `root_id`, `name`, `type`. These four fields are sufficient to display search results and perform the SQLite join-table lookup without an additional graph store round-trip.

## Considered Options

- **Dedicated `mcp_vectors_entities` collection, `QdrantEntities` class** *(chosen)* — follows the established pattern; entity lifecycle (write, search, cleanup, feature-toggle) is fully isolated; no risk of entity search accidentally matching chunk points.
- **Pack into `mcp_vectors` with `point_type: "entity"` filter** — one fewer collection; adds filter overhead to every entity search; entity cleanup must distinguish entity points from chunk points in the same collection; reasoning about collection contents becomes harder over time.
- **Pack into `mcp_vectors_communities`** — wrong lifecycle alignment; communities are scoped by detection build while entity embeddings are stable across builds; rejected without further analysis.

## Consequences

- Qdrant now manages three collections: `mcp_vectors`, `mcp_vectors_communities`, `mcp_vectors_entities`. The pattern is one collection per object type with distinct lifecycle.
- `ENTITY_EXTRACTION=false` cleanly bypasses `QdrantEntities` initialization; no orphaned data in shared collections.
- Entity cleanup on file removal deletes by `filter(root_id=X, entity_id IN [...])` within the entities collection only — no risk of touching chunk or community points.
- `QdrantEntities` is initialized alongside `QdrantCommunities` in `RAGPipeline.initialize()` when `ENTITY_EXTRACTION=true`.
- **Model/dimension invariant**: entity embeddings in `mcp_vectors_entities` and query embeddings at `search_global` time must use the same model and vector dimension. If `EMBEDDING_MODEL` is changed, all existing entity points are stale and must be re-embedded before targeted search is reliable. The correct remediation is `clear_index` (which drops the entities collection via ADR-0013 Tier 2) followed by re-indexing, which re-extracts and re-embeds all entities with the new model.
