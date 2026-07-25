# Two-Tier Entity Cleanup on Index Removal

## Context

ADR-0012 introduced a dedicated `mcp_vectors_entities` Qdrant collection. When indexed content is removed, entity embeddings in that collection can become orphaned. Two distinct removal paths exist today:

- **Single-file removal** (`remove_document`): deletes chunk points from `mcp_vectors` and calls `graph_store.delete_file_entities` to prune the file's entities from SQLite. It has no path to delete entity points from the new entities collection.
- **Full-root clear** (`clear_index`): deletes chunk points only. It does **not** clean the SQLite graph store at all (a pre-existing gap), nor the entities collection.

Two properties of the entity model shape the options:
- Entity IDs are **deterministic**: `entity_id = hash(name + type + root_id)`. Re-extracting the same entity produces the same Qdrant point ID, so an upsert overwrites rather than duplicates.
- The entity→community resolution at query time goes through the SQLite join table scoped by the current `build_id` (ADR-0010). An entity Qdrant point with no matching join-table row for the current build contributes no community candidates.

## Decision

Adopt asymmetric, two-tier cleanup:

**Tier 1 — Single-file removal: lazy, no explicit Qdrant entity deletion.**
`remove_document` continues to prune SQLite entities only. Orphaned entity Qdrant points are left in place. They are harmless: at query time the build-scoped join table never maps them to a community, and any future re-extraction of the same entity overwrites the point by deterministic ID.

**Tier 2 — Full-root clear: explicit deletion of both stores.**
When `clear_index` resolves to a full root, it additionally:
1. Calls `QdrantEntities.delete_by_root_id(root_id)` — one Qdrant delete-by-filter on `root_id`.
2. Calls `graph_store.drop_root(root_id)` — deletes the root's SQLite graph DB file (and WAL/SHM sidecars) and its registry entry. This method already exists and is idempotent.

Tier 2 also closes the pre-existing gap where `clear_index` left the entire SQLite graph state behind.

## Considered Options

- **Explicit per-entity Qdrant deletion in `remove_document`** — precise, no orphans ever. Requires `delete_file_entities` to return the affected entity IDs instead of a count (a signature/behavior change), and a per-ID Qdrant delete. Rejected: orphans are provably harmless and self-healing, so the added coupling is not justified.
- **Lazy everywhere, including root clear** — simplest. Rejected for the root case: a cleared root is never re-extracted, so its orphans never self-heal and accumulate indefinitely in Qdrant and SQLite.
- **Two-tier: lazy file removal + explicit root clear** *(chosen)* — matches cleanup effort to whether self-healing can occur. Single-file orphans self-heal; root-clear orphans cannot, so they are deleted explicitly.

## Consequences

- `remove_document` is unchanged for entities; no new failure modes on the hot file-removal path.
- `clear_index` gains two cleanup calls when the target is a full root, and now leaves no graph state behind — a behavior improvement beyond the entities feature.
- Orphaned single-file entity points persist until overwritten or until the root is cleared. This is an accepted, bounded cost: the count is limited by entities unique to removed-and-not-re-added files, and none affect query correctness.
- `QdrantEntities` must expose `delete_by_root_id(root_id)` mirroring the delete-by-filter pattern used elsewhere.
- Determining whether a `clear_index` target "resolves to a full root" requires a root-boundary check; partial-path clears remain lazy (Tier 1 semantics) since the root still exists and entities may be re-added.
