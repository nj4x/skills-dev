# Entity-to-Community Reverse Mapping in SQLite Join Table

## Context

ADR-0009 established that entity embeddings are stored in Qdrant at extraction time to enable semantic entity search. At `search_global` time, the top-K semantically matched entities must be resolved to their community IDs so that only those communities are summarized (avoiding the full O(N-communities) batch).

The existing `communities` table stores `entity_ids TEXT` — a serialized JSON list on each community row. This is the forward direction (community → entities) and is what detection already produces. There is no reverse index: entities have no `community_id` field, and looking up which community an entity belongs to requires scanning every community row and deserializing JSON — O(all communities), which defeats the optimization.

There is also a timing constraint: entity embeddings are written during extraction (background, immediately after `_extract_and_merge`), but community assignments (`entity_ids` per cluster) are not known until detection commits a build. The reverse mapping can only be populated after detection, not at extraction time.

## Decision

Detection commits a new `entity_community(entity_id, community_id, root_id, build_id)` join table to the SQLite graph store when it writes each build. Detection already iterates every cluster's `entity_ids`; it writes the reverse tuples as part of that same commit.

At `search_global` time:
1. Embed the query (already done).
2. Semantic-search entity embeddings in Qdrant → top-K `entity_id`s.
3. `SELECT DISTINCT community_id FROM entity_community WHERE entity_id IN (…) AND root_id = ? AND build_id = ?` — one indexed SQLite query.
4. Trigger `schedule_reports` only for those community IDs.

The join table is scoped by `(root_id, build_id)` so stale rows from prior detection builds are naturally ignored by the build_id filter and can be garbage-collected when a new build commits.

## Considered Options

- **SQLite join table at detection time** *(chosen)* — reverse mapping written when community assignments are known; zero Qdrant backfill; query path is two fast hops (Qdrant → SQLite); entity embedding timing stays at extraction as decided.
- **Community ID as Qdrant payload, backfilled at detection** — single Qdrant round-trip at query time; requires detection to patch already-written Qdrant points, introducing cross-phase coupling between extraction and detection writes.
- **Embed entities at detection time, not extraction** — eliminates timing mismatch; community ID available at write time; contradicts the eagerness decision (ADR-0009) and delays entity searchability until detection completes.

## Consequences

- Detection gains a write responsibility: after committing cluster structure, it also populates `entity_community` rows. Detection already holds the entity-to-cluster assignment in memory at that moment, so this is a cheap addition.
- Query path adds one SQLite `IN` lookup after entity Qdrant search. Both hops are fast; the SQLite query is an indexed point lookup, not a scan.
- Stale rows from prior builds accumulate until garbage-collected. GC can run at detection commit time by deleting rows where `build_id != new_build_id` for the same `root_id`.
- `entity_community` must be rebuilt on every detection build change (when cluster assignments shift). This is correct: community membership is a property of a detection build, not a permanent entity attribute.
