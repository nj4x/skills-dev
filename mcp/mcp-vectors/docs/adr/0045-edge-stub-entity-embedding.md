# ADR-0045: Embed Edge-Stub Entities into Qdrant

## Status

Approved

## Context

During entity graph indexing, `replace_file_entity_map()` creates "edge-stub" entities in SQLite for edge endpoints that don't appear in the extracted entity map. These stubs maintain referential integrity but were **never embedded to Qdrant**, creating:
- **Coverage gaps**: Qdrant queries miss stub entities; entity-graph reranking cannot resolve them.
- **Orphaned records**: SQLite has entities with no corresponding Qdrant vectors.
- **Hidden inconsistency**: stats show 100% "embedded" while stubs are silently missing.

## Decision

Embed edge-stub entities into Qdrant alongside regular entities:

1. **Return stub info from `replace_file_entity_map()`**: return `(version, stubs, deleted_ids)` where stubs are dicts `{"id": eid, "name": name, "type": type}`.
2. **Embed in `_extract_and_merge()`**: after graph update, embed stubs using the same async `_embed_stub()` closure and embedding semaphore as regular entities.
3. **Consistent error handling**: stub embedding failures follow the same error-accumulation pattern (per-signature warnings + count summary).
4. **Empty descriptions**: stubs have `description=""` in SQLite; embedding text is derived from name and type only.

Benefits:
- Keeps `GraphStore` synchronous (no async dependency).
- Stubs are embedded with regular entities, using shared semaphore and error handling.
- Consistent identity via [[0043-entity-identity-centralization]].

## Consequences

✅ **Complete coverage**: every entity in SQLite has a Qdrant vector.
✅ **Consistent error tracking**: stub failures counted alongside entity failures.
✅ **Observability**: entity-graph reranking can resolve all named entities.
⚠️ **Minor LM cost**: one embedding per stub entity (amortized over file batches).

## Related

- [[0043-entity-identity-centralization]]: stub IDs computed using centralized formula.
- [[0044-stale-entity-vectors-cleanup]]: stale stubs cleaned via same deletion path.
- [[0046-entity-coverage-metrics]]: stubs included in `entities_total` count.
