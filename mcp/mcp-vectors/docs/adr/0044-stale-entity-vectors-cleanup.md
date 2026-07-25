# ADR-0044: Asynchronous Cleanup of Stale Entity Vectors on Re-Index

## Status

Approved — implementation (commit 41ac5a0) has a known live defect: re-indexing any file erases all
single-file entities' and stubs' vectors immediately after they are upserted, inverting the intended
outcome and creating a net regression versus not shipping this ADR. The lowest-risk remediation
(disabling the delete entirely, option (e)) was not selected at implementation time. No tracking
issue exists; the defect is unowned.

## Context

When a file is re-indexed, `_purge_file_contributions()` deletes entities from SQLite whose only source was that file. However, their vectors remain orphaned in Qdrant's `mcp_vectors_entities` collection. An orphan is a Qdrant point with no corresponding SQLite row. This creates two real problems:
- **False positives in entity search**: semantic search over `mcp_vectors_entities` returns orphaned
  points; they appear in nearest-neighbour results for queries even though the entity no longer
  exists in the graph. (ADR-0013's build-scoped join table mitigates this for community-report
  targeting, but any direct entity-vector search is unfiltered.)
- **Dead data accumulation**: stale vectors grow unbounded; there is no periodic sweep.

Note: the original bullets ("coverage gaps", "observability loss") were inverted. Orphans are extra
Qdrant points — they cause surplus data, not missing data. Deleting vectors cannot make deleted
entities findable.

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

This can be derived from the code: `_purge_file_contributions()` returns all entities whose only
source file was the re-indexed file (graph_store.py:478-506); `replace_file_entity_map()` then
re-inserts matching entities in SQLite (graph_store.py:763-774) and returns stubs with identical
IDs (graph_store.py:798-822); and `_extract_and_merge()` calls `delete_by_entity_ids` after all
upserts complete (rag.py:844). The three operations preserve the overlap by design.

The hidden assumption behind the original decision — that `deleted_ids` is disjoint from the
entities re-created in the same transaction — is false. The ADR's claim that "cleanup happens after
SQLite commit ensures atomicity" addressed the wrong ordering; the ordering that matters is
cleanup relative to the **embed upserts**, not relative to the commit.

This defect is accepted as known and unfixed at the time of writing. Proposed remediations:

**(a) Set-difference deletion** (compute `deleted_ids − re-inserted_ids` in `replace_file_entity_map`):
the narrowest viable option for same-file re-index. Narrows (but does not close) the cross-file window.

**(b) Delete before embed**: reorder the calls so deletes run before the embed gathers. Makes same-file
re-index harmless at the cost of a redundant delete+write per surviving entity. Does not address the
cross-file concurrency window. Also leaves unobservable divergence if the process crashes or shuts down
between the SQLite COMMIT and the fire-and-forget Qdrant delete.

**(c) Re-check SQLite existence immediately before Qdrant delete**: skip IDs that have been
re-inserted since the transaction. This is itself a TOCTOU race — the path lock is released before
the background `_extract_and_merge` task fires (rag.py:608, released at :687; task fires at :687),
so nothing spans both stores. An entity can be re-inserted between the check and the delete.
Narrows the window; does not close it.

**(d) Gate deletion on `graph_version` at delete time**: unworkable. `graph_version` is a single
per-root counter in the meta table (graph_store.py:117-120) with PK `root_id`, bumped by every
`replace_file_entity_map` call (:867-870). It has zero per-entity granularity. Under concurrent
re-index, the version advances before nearly every async delete fires, so a version gate would
suppress essentially all cleanup rather than make deletion safe. Would require per-entity
versioning to be viable.

**(e) Disable the delete entirely** (remove the `delete_by_entity_ids` call from
`_extract_and_merge`): eliminates the regression for single-file and stub vectors on re-index,
restoring the state prior to this ADR. Orphans from genuine entity removal (all source files gone)
would remain in Qdrant until the next full `clear_index` — consistent with ADR-0013's Tier 2
approach. This is the least-risk remediation if the re-index path's correctness is the priority;
the "stale vectors accumulate" consequence is the same as pre-ADR-0044 state.

None of the immediate remediations fully close the window. A safe design requires either
per-entity versioning, a persistent tombstone table with async drain, or a reconciliation sweep
that detects and removes Qdrant orphans independently of the re-index path.

## Alternatives considered

See "Known defect" section for detailed evaluation of remediations (a)-(d). At a higher level:

- **Periodic reconciliation sweep** (walk SQLite ids vs. Qdrant point ids per root, delete the
  difference): self-healing, covers file deletion and crash-interrupted runs, and subsumes the
  entire delete-on-re-index mechanism. Rejected for the overhead of a scheduler and a full scan
  per root per reconciliation cycle, and unbounded staleness between sweeps.
- **Tombstone table** (record deleted IDs in SQLite, drain asynchronously with retry): survives
  process restart and makes failed deletes recoverable. Requires a new table, a drain worker, and
  extra write amplification on every re-index. More complex than the current best-effort delete-on-re-index,
  but fundamentally safer (no TOCTOU or concurrency window).
- **Per-entity versioning**: attach a generation counter to each entity ID in Qdrant's payload,
  compare at delete time to skip IDs whose version has advanced since the deletion set was captured.
  Requires schema changes and version bumping on every re-insert. Would close the concurrency window
  but is higher overhead than current.

## Consequences

⚠️ **Net regression for single-file entities and stubs (known defect)**: re-indexing a file deletes
the vectors of every entity/stub whose sole source is that file, even those re-inserted moments
earlier in the same transaction — see "Known defect" above. The net outcome is zero Qdrant vectors
where there were stale-but-present vectors before shipping this ADR. This is a regression; entities
with multiple source files are kept (trimmed, not deleted), and the file-deletion path
(`delete_file_entities`) explicitly does not call `delete_by_entity_ids`. Single-file re-index
remains the primary case where this ADR runs.
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
- Zero-entity re-index: `delete_by_entity_ids` is gated only on `deleted_ids` being non-empty
  and `_qdrant_entities` being initialized (rag.py:841-842). The embed block is gated additionally
  on `entity_map.entities` being truthy (rag.py:753). If a re-indexed file now yields zero entities,
  the embed block is skipped (no re-upsert), but `deleted_ids` is non-empty (entities that existed
  for this file before), so the delete block runs and permanently destroys all prior entity and stub
  vectors for that file with no compensating write. This is a distinct regression from the
  delete-after-upsert overlap; it affects files whose entity content has been removed or whose LLM
  extraction returned empty on this pass.
- `remove_document` / `delete_file_entities` path leaves orphaned vectors.
- `extract_entities_from_file` performs no cleanup at all.
- Delete failures are unobservable in practice (swallowed inside the Qdrant helper).
- `delete_by_entity_ids` (qdrant.py:1380-1391) sends all entity IDs in a single unbatched
  `PointIdsList` to Qdrant. `_purge_file_contributions` (graph_store.py:495-498) issues a single
  unchunked SQL `DELETE FROM edge_contributions WHERE (source_id IN (...) OR target_id IN (...))`,
  binding 2N+1 parameters where N is the entity count. Entities are deleted one at a time
  (graph_store.py:499-504). A large single-file purge can exceed SQLITE_MAX_VARIABLE_NUMBER (999
  on installations before SQLite 3.32, 32766+ on 3.32+), aborting the entire transaction. The Qdrant
  request may also be rejected silently (swallowed by the internal exception handler).
- Graceful shutdown mid-extraction: `RAGPipeline.close()` cancels in-flight extraction tasks via
  `CancelledError` (a `BaseException`), which passes through all `except Exception` handlers in the
  embed and delete paths. This deterministically leaves the SQLite transaction committed while the
  async Qdrant delete is never attempted — creating permanent orphans. No repair or recovery path.
  Same risk applies to any task cancellation between the SQLite COMMIT and the fire-and-forget
  async delete call.
- `RegistryReconciler` startup purge/remap: `_apply_vector_phase` calls `vector_store.remap_root`
  for `SERVING_REMAPPED` roots and `vector_store.delete_root` for `SERVING_PURGED` roots
  (reconciliation.py:347-359); `_apply_graph_phase` calls `graph_store.drop_root` for both states
  (:374-376). Neither phase calls `_qdrant_entities.delete_by_root_id`. Entity vectors for affected
  roots are left orphaned in `mcp_vectors_entities`. For `SERVING_REMAPPED` roots this is permanent:
  the canonical `root_id` changes, so the old root's entity digests can never be overwritten by
  re-indexing under the new root. For `SERVING_PURGED` roots, orphans are recoverable if the root
  is subsequently re-indexed (same `root_id` → same digests → upsert overwrites), but permanent if
  the root is never re-indexed. Only `clear_index` triggers `delete_by_root_id` (rag.py:1512);
  reconciliation is a silent orphan source for both states.

## Related

- [[0043-entity-identity-centralization]]: depends on centralized identity for targeted deletion.
- [[0045-edge-stub-entity-embedding]]: introduced the stubs list (second return value of
  `replace_file_entity_map`); this ADR added `deleted_ids` as the third.
- [[0013-two-tier-entity-cleanup-on-removal]] (root `docs/adr/`): ADR-0013 explicitly considered
  and rejected per-entity Qdrant deletion from the file-removal path, arguing orphans are
  "provably harmless and self-healing" via deterministic IDs. This ADR's mechanism implements
  exactly the pattern ADR-0013 rejected, applied at the re-index path instead of `remove_document`.
  The two approaches are in direct tension: ADR-0013's self-healing argument holds for entities
  that survive re-index (deterministic ID means the re-embed overwrites the orphan), but breaks for
  entities truly removed from all files (where the orphan persists until `clear_index`). This ADR
  targets the latter case; its delete-after-upsert defect causes a regression for the former.
