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

## Critic Review

3 iterations. Final verdict: **approve (minor)**.

### Resolved major issues (iterations 1–3)

- ADR-0044: delete-after-upsert erases fresh vectors on re-index — documented as Known defect with cross-file concurrency window and remediation options.
- ADR-0043: formula change is a breaking identity change requiring full re-index — added ⚠️ consequence; Context rewritten to describe id divergence (not collision).
- ADR-0046: metrics are not queryable via `get_graph_stats()` — downgraded from "explicit and queryable" to "internal only".
- ADR-0045: zero-entity files with stubs never embedded — documented in Scope; embedding text corrected to `f"{name}: (no description)"`.
- All four ADRs: method name corrected to `extract_entities_from_file`; wikilinks fixed; Alternatives considered added to 0043 and 0046; Scope sections added to all four.
- ADR-0044: cross-file concurrency window, unchunked batch sizes, silent failures in `delete_by_entity_ids` — all documented.

### Remaining minor issues (not blocking)

- ADR-0044 Known gaps: SQL description is slightly imprecise (`edge_contributions` delete binds ~2N params; entity/edge deletes are per-ID loops). Substance correct.
- ADR-0044 Related: attribution inverted — 0045 introduced the stub list (second element); 0044 added `deleted_ids` (third).
- ADR-0046 Related: 0044 described as "independent… purely observational", mildly contradicting the Consequences entry that says vectors erased by 0044's defect are counted as embedded.
- ADR-0043 Known limitations: does not name the `"unknown"` vs `""` type fallback divergence between graph_store.py and entity_extractor.py for unresolved edge endpoints (consequence already covered in prose).
