# ADR-0044: Asynchronous Cleanup of Stale Entity Vectors on Re-Index

## Status

Approved — implementation defective; remediation (delete-before-embed reorder) is the recommended
interim fix. No tracking issue exists at the time of writing.

## Context

When a file is re-indexed, `_purge_file_contributions()` deletes entities from SQLite whose only source was that file. However, their vectors remain orphaned in Qdrant's `mcp_vectors_entities` collection, creating:
- **Coverage gaps**: community reports query Qdrant and miss orphaned entities.
- **Dead data**: stale vectors accumulate and never get cleaned.
- **Observability loss**: entity-graph reranking cannot find entities that were deleted.

The function `QdrantEntities.delete_by_entity_ids()` exists but is never called — it was stubbed as "reserved for future use." (Its docstring in `vectors/qdrant.py` still carries that "reserved for future use" wording even though it is now wired; the comment is stale.)

## Decision

Wire `delete_by_entity_ids()` into the re-index cleanup path:

1. **Return deleted IDs from `_purge_file_contributions()`**: track entity IDs that are being deleted during SQLite cleanup.
2. **Propagate to caller**: `replace_file_entity_map()` returns `(version, stubs, deleted_ids)`.
3. **Async cleanup in `_extract_and_merge()`**: after graph update completes, call `await _qdrant_entities.delete_by_entity_ids(root_id, deleted_ids)`.
4. **Best-effort**: cleanup failures do not block extraction.

Benefits:
- Keeps `GraphStore` synchronous (no async I/O).
- Cleanup runs after the SQLite transaction has committed, so the delete set reflects durable state.
- Non-fatal: a Qdrant outage cannot fail an index operation.

## Scope

Cleanup is wired in **exactly one** call path: `RAGPipeline._extract_and_merge()`.

Not wired:
- `extract_entities_from_file()` (`vectors/rag.py`) calls `replace_file_entity_map` and discards all
  three return values — no stale-vector deletion happens on that path.
  Note: `extract_entities_from_file` currently has no callers anywhere in the repository (no MCP
  tool, no test invokes it directly); the coverage gap is latent rather than active. If this method
  is not intended to be reachable it should be removed rather than documented as an unwired path.
- `GraphStore.merge_entity_map()` delegates to `replace_file_entity_map` and discards stubs and
  deleted IDs by design (it returns only `graph_version`).
- `remove_document()` → `GraphStore.delete_file_entities()` (file deletion / un-indexing) removes
  entities from SQLite but never touches Qdrant. See "Known gaps".

## Known defect: delete-after-upsert erases fresh vectors

`_purge_file_contributions()` returns **every** entity whose only source file was the re-indexed
file — including entities and stubs that are re-inserted with identical IDs later in the same
transaction. It is a "sole source was this file" set, not a "genuinely gone" set.

In `_extract_and_merge()` the ordering is: embed entities → embed stubs → `delete_by_entity_ids`.
Because the delete runs *after* the upserts and the ID sets overlap, re-indexing a file deletes the
vectors that were just written for it.

Reproduced empirically: indexing the same file twice returns `deleted_ids` containing exactly the
IDs that were re-inserted and re-embedded on that same run. Net effect for any single-file entity
or stub after a re-index: **no vector at all**, which is the inverse of the intended outcome.

The hidden assumption behind the original decision — that `deleted_ids` is disjoint from the
entities re-created in the same transaction — is false. The ADR's claim that "cleanup happens after
SQLite commit ensures atomicity" addressed the wrong ordering; the ordering that matters is
cleanup relative to the **embed upserts**, not relative to the commit.

This defect is accepted as known and unfixed at the time of writing. Remediation is either
(a) subtracting the re-inserted entity + stub IDs from `deleted_entity_ids` inside
`replace_file_entity_map`, or (b) moving the `delete_by_entity_ids` call ahead of the embed gathers.

Neither remediation closes the cross-file concurrency window: `deleted_ids` is a transaction-time
snapshot from file A's SQLite write, but the Qdrant delete fires asynchronously after any number of
concurrent `_extract_and_merge` tasks (rag.py fires one `asyncio.ensure_future` per file with no
cross-file concurrency limit). If file B concurrently re-creates an entity whose sole prior source
was file A, A's later `delete_by_entity_ids` call removes B's fresh vector — a live SQLite entity
with no Qdrant point. A genuinely safe fix requires either (c) re-checking SQLite existence
immediately before the Qdrant delete (to skip IDs still present), or (d) gating deletion on
`graph_version` at delete time. Remediation (a) narrows but does not close this window; remediation
(b) does not address it at all.

## Alternatives considered

- **Set-difference deletion** (compute `deleted_ids − re-inserted_ids` in `replace_file_entity_map`):
  the narrowest correct fix, keeps a single write path. Rejected only because it was not identified
  before implementation; it is now the recommended remediation.
- **Delete before embed**: trivially reorders the existing calls and makes overlap harmless, since
  re-inserted entities are simply re-upserted afterwards. Costs a redundant delete+write per
  surviving entity.
- **Periodic reconciliation sweep** (walk SQLite ids vs. Qdrant point ids per root, delete the
  difference): self-healing and covers file deletion and crash-interrupted runs too, but needs a
  scheduler, a full scan per root, and gives unbounded staleness between sweeps.
- **Tombstone table** (record deleted IDs in SQLite, drain asynchronously with retry): survives
  process restart and makes failed deletes recoverable, at the cost of a new table, a drain worker,
  and extra write amplification on every re-index.

## Consequences

⚠️ **Partial cleanup (known defect)**: on re-index, entities and stubs whose sole source is the same
file have their newly written vectors deleted immediately after upsert — see "Known defect" above.
Entities that genuinely disappear *are* removed, so the mechanism does remove true orphans; it just
over-deletes live ones.
⚠️ **Best-effort with silent failures**: `QdrantEntities.delete_by_entity_ids` catches every
exception internally, logs a generic best-effort warning without file context, and returns `None`.
The caller's `try/except` in `_extract_and_merge` is therefore dead code and its file-path-scoped
warning can never fire. The method also returns early and silently when `not self._initialized`,
dropping an entire delete batch with zero logging.
⚠️ **Unaddressed orphan source**: file deletion (`remove_document` → `delete_file_entities`) leaves
Qdrant vectors orphaned. In normal operation this is the more common orphan source than re-index.
✅ **Architectural separation**: concerns stay clean (sync SQLite ops in `GraphStore`, async Qdrant
ops in the pipeline); `GraphStore` acquires no async dependency.
⚠️ **No test coverage**: no test exercises the wired cleanup path. The existing suite passes because
this behavior is never invoked in tests. A regression test should re-index an unchanged file and
assert `deleted_ids` is disjoint from the returned entity/stub IDs and that the entity's Qdrant
point survives.

## Known gaps

- Delete-after-upsert overlap (above) — the dominant correctness issue.
- `remove_document` / `delete_file_entities` path leaves orphaned vectors.
- `extract_entities_from_file` performs no cleanup at all.
- Delete failures are unobservable in practice (swallowed inside the Qdrant helper).
- Both `delete_by_entity_ids` (qdrant.py) and `_purge_file_contributions` (graph_store.py) issue
  unchunked batch operations: all IDs in a single Qdrant `PointIdsList` and all IDs in a single SQL
  `DELETE ... WHERE id IN (...)`. A large single-file purge can exceed SQLITE_MAX_VARIABLE_NUMBER,
  aborting the entire re-index transaction, or produce an oversized Qdrant request that is rejected
  silently (swallowed by the internal exception handler).

## Related

- [[0043-entity-identity-centralization]]: depends on centralized identity for targeted deletion.
- [[0045-edge-stub-entity-embedding]]: tuple expansion adds third return value.
