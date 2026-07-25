# Join Table Rows Cleaned Eagerly on New Build; Entity Rows Are Lazy

## Context

The `entity_community` join table (ADR-0010) accumulates rows across detection builds: each build writes `(entity_id, community_id, root_id, build_id)` tuples. Over time, rows from prior builds become stale (the cluster assignments have changed). Separately, entity rows in SQLite and Qdrant may become orphaned when files are removed from the index.

Two distinct cleanup questions arise:
1. When should stale join-table rows (from prior detection builds) be cleaned up?
2. When should orphaned entity rows (for deleted files) be cleaned from SQLite and Qdrant?

## Decision

**Join table: eager cleanup on new detection build.**
When detection commits a new build, it deletes all join-table rows for the root that do not belong to the new build:

```sql
DELETE FROM entity_community WHERE root_id = ? AND build_id != ?
```

Only the current build's rows are retained. This keeps the join table bounded (proportional to current cluster assignments, not detection build count).

**Interaction with ADR-0017.** ADR-0017 states targeting queries the join table without a `build_id` filter. This eager DELETE means that in steady state only current-build rows exist, so the absent filter is normally a no-op. ADR-0017's benefit is confined to the in-progress-rebuild window: the new build's rows are written and its cleanup DELETE runs within the detection commit transaction, so prior-build rows remain visible to targeting until that transaction commits. ADR-0017 does not depend on cross-build rows surviving a completed build — this ADR guarantees they do not.

**Entity rows: lazy, rely on self-healing.**
Detection does NOT explicitly prune orphaned entity rows from SQLite or Qdrant. Orphaned entity rows (for files removed from the index) are left in place. They are harmless: entity search may return them, but with no join-table rows for the current build, they contribute no community candidates at query time. Deterministic entity IDs (ADR-0009) mean re-extraction of a returning file overwrites the same row by ID. The full-root clear (`clear_index` for a full root, ADR-0013) is the only guaranteed cleanup path for orphaned entity rows.

## Considered Options

**For the join table:**
- **Lazy accumulation** — stale rows persist until root clear; inert at query time (scoped by build_id); no cleanup overhead. Rejected: join table grows without bound across detection builds; bounded cleanup is cheap and correct.
- **Eager cleanup on new build** *(chosen)* — one DELETE per root per build; bounded size; rows are only from the current build.
- **Periodic GC task** — decoupled from detection; eventual consistency; adds scheduling infrastructure. Rejected: eager cleanup is simpler and equally correct.

**For entity rows:**
- **Explicit orphan detection and deletion** — precise; requires cross-referencing entity file_paths against indexed file set; complex; introduces dependency between extraction and file inventory.
- **Stale marking on file removal** — requires new schema column; threshold for "old enough to purge" is a tuning knob.
- **Lazy, rely on self-healing** *(chosen)* — orphaned entity rows are inert (no join-table rows map them to communities); deterministic IDs handle re-adds; no cleanup logic needed at the entity level.

## Consequences

- The join table remains bounded at O(current entity count × average communities per entity) across any number of detection builds.
- Detection gains one DELETE call per new build commit: `DELETE FROM entity_community WHERE root_id = ? AND build_id != ?`. This is fast (index-scoped delete) and part of the detection commit transaction.
- Orphaned entity rows in SQLite and Qdrant persist indefinitely until the root is cleared. Their count is bounded by the number of entities from removed-and-never-re-added files. This is an accepted, bounded cost.
- Entity Qdrant points from orphaned entities may be returned by entity search, but with no join-table row they contribute no community candidates — they are invisible to targeting at query time.
- The asymmetry (eager join table, lazy entities) is intentional: join-table staleness directly affects targeting correctness (wrong community IDs); entity row staleness does not (filtered out by the join table).
