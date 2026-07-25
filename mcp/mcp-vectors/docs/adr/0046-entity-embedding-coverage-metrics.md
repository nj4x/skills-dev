# ADR-0046: Entity Embedding Coverage Metrics in GraphificationStats

## Status

Approved

## Context

The `GraphificationStats` dataclass tracked `entities_found` (extracted count) and `entities_embed_failed` (failure count), but had **no visibility** into:
- Whether embedding is enabled (`_qdrant_entities` is None/initialized).
- How many entities were successfully embedded (only failures tracked).
- Total entity scope (extracted entities + edge-stub entities).

This made it impossible to answer: "What is our embedding coverage for this file?"

## Decision

Add three fields to `GraphificationStats`, updated during `_extract_and_merge()`:

```python
@dataclass
class GraphificationStats:
    entity_embedding_enabled: bool = False  # _qdrant_entities is not None
    entities_embedded: int = 0              # successful upserts (entities + stubs)
    entities_total: int = 0                 # scope (entities_found + num_stubs)
    # ... existing fields ...
```

- `entity_embedding_enabled`: set to `True` once per file if `_qdrant_entities` is not None.
- `entities_embedded`: incremented for each successful entity/stub upsert (independent counter, not sum of failures/successes).
- `entities_total`: sum of extracted entities and edge-stub entities created during re-indexing.

Coverage is computed as: `entities_embedded / entities_total` (when `entity_embedding_enabled=True`).

## Consequences

✅ **Complete observability**: coverage metrics are explicit and queryable.
✅ **Per-file tracking**: metrics update per extraction, enabling real-time monitoring.
✅ **Failure recovery visibility**: gaps between `entities_total` and `entities_embedded` highlight embedding failures.
✅ **No performance cost**: counters are simple increments in the embedding loop.

## Related

- [[0043-entity-identity-centralization]]: used for consistent entity identity.
- [[0045-edge-stub-entity-embedding]]: stubs included in `entities_total` and `entities_embedded`.
- [[0044-stale-entity-vectors-cleanup]]: independent of stub/stale cleanup; purely observational.
