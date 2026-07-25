# Design Decisions Reached During Grilling

Entity identity centralization and embedding integrity fix for mcp-vectors (scope B).

## Implementation Summary

Four interconnected architectural decisions to fix recurring entity embedding failures:

1. **Centralize entity identity formula** (ADR-0043)
   - Single source of truth: `graph_store.entity_id(name, type_, root_id)`
   - Mandatory type coercion: `(type_ or "").strip().lower()`
   - Replaces three-location formula inconsistency

2. **Asynchronous stale vector cleanup** (ADR-0044)
   - `_purge_file_contributions()` returns deleted entity IDs
   - `replace_file_entity_map()` returns `(version, stubs, deleted_ids)`
   - `_extract_and_merge()` calls `delete_by_entity_ids()` after graph update

3. **Embed edge-stub entities** (ADR-0045)
   - Edge-stubs tracked during `replace_file_entity_map()`
   - Embedded in `_extract_and_merge()` with regular entities
   - Consistent error handling; failures follow existing diagnostics pattern

4. **Add coverage metrics** (ADR-0046)
   - `GraphificationStats.entity_embedding_enabled: bool`
   - `GraphificationStats.entities_embedded: int`
   - `GraphificationStats.entities_total: int`

## Affected Files

- `vectors/graph_store.py` — centralized identity, stub tracking, deletion return values
- `vectors/entity_extractor.py` — import centralized identity
- `vectors/rag.py` — import centralized identity, embed stubs, delete stale vectors, track coverage
- `tests/test_graph_store.py` — update imports and assertions
- `tests/test_entity_embed_failures.py` — update mock signatures
- `tests/test_entity_backfill.py` — update mock return values

## Testing

- All 559 existing tests pass post-implementation
- No new test files added (existing test coverage sufficient)
- Mock signatures updated to reflect 3-tuple returns

## Commits

- 085d9da refactor: centralize entity identity formula in graph_store.entity_id
- 209a8da feat: embed edge-stub entities into Qdrant during graph indexing
- 41ac5a0 feat: clean up stale entity vectors on re-index
- 37e007f feat: add entity embedding coverage counters to GraphificationStats

## ADR Files

- docs/adr/0043-entity-identity-centralization.md
- docs/adr/0044-stale-entity-vectors-cleanup.md
- docs/adr/0045-edge-stub-entity-embedding.md
- docs/adr/0046-entity-embedding-coverage-metrics.md
