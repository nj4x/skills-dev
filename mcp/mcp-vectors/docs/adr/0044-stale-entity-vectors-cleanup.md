# ADR-0044: Asynchronous Cleanup of Stale Entity Vectors on Re-Index

## Status

Approved

## Context

When a file is re-indexed, `_purge_file_contributions()` deletes entities from SQLite whose only source was that file. However, their vectors remain orphaned in Qdrant's `mcp_vectors_entities` collection, creating:
- **Coverage gaps**: community reports query Qdrant and miss orphaned entities.
- **Dead data**: stale vectors accumulate and never get cleaned.
- **Observability loss**: entity-graph reranking cannot find entities that were deleted.

The function `QdrantEntities.delete_by_entity_ids()` exists but is never called — it was stubbed as "reserved for future use."

## Decision

Wire `delete_by_entity_ids()` into the re-index cleanup path:

1. **Return deleted IDs from `_purge_file_contributions()`**: track entity IDs that are being deleted during SQLite cleanup.
2. **Propagate to caller**: `replace_file_entity_map()` returns `(version, stubs, deleted_ids)`.
3. **Async cleanup in `_extract_and_merge()`**: after graph update completes, call `await _qdrant_entities.delete_by_entity_ids(root_id, deleted_ids)`.
4. **Best-effort**: failures are logged but do not block extraction.

Benefits:
- Keeps `GraphStore` synchronous (no async I/O).
- Cleanup happens **after** SQLite commit ensures atomicity.
- Failures are observable but non-fatal.

## Consequences

✅ **Complete cleanup**: no orphaned vectors on re-index.
✅ **Observability**: failures logged with context (file path, error type).
✅ **Architectural separation**: concerns stay clean (sync DB ops, async Qdrant ops).
⚠️ **Eventual consistency**: stale vectors persist until the next re-index.

## Related

- [[0043-entity-identity-centralization]]: depends on centralized identity for targeted deletion.
- [[0045-edge-stub-embedding]]: tuple expansion adds third return value.
