# Entity-Targeted Summarization: ADR Manifest

Design for semantic entity search via Qdrant to narrow community summarization in `search_global`, reducing first-query latency from O(all communities) to O(targeted communities).

## ADRs Produced in This Session

### Core design (9–15)

- [ADR-0009: Entity Embeddings in Qdrant](../docs/adr/0009-entity-embeddings-in-qdrant.md)
  Embed entities eagerly during extraction (name + description); store in dedicated Qdrant collection keyed by (root_id, entity_id).

- [ADR-0010: Entity-to-Community Reverse Mapping in SQLite](../docs/adr/0010-entity-community-reverse-mapping-in-sqlite.md)
  Detection writes `entity_community(entity_id, community_id, root_id, build_id)` join table; query path is Qdrant entity search → SQLite IN lookup → community IDs.

- [ADR-0011: Entity Search Scope — K=20, 30% Cap, Zero-Match Fallback](../docs/adr/0011-entity-search-scope-and-fallback.md)
  Retrieve top-20 entities; if targeted communities exceed 30% of total, fall back to full summarization; zero-match falls back immediately.

- [ADR-0012: Dedicated mcp_vectors_entities Qdrant Collection](../docs/adr/0012-mcp-vectors-entities-qdrant-collection.md)
  New `mcp_vectors_entities` collection + `QdrantEntities` class; entity lifecycle is fully isolated from chunks and community reports.

- [ADR-0013: Two-Tier Entity Cleanup on Index Removal](../docs/adr/0013-two-tier-entity-cleanup-on-removal.md)
  Single-file removal: lazy (orphans are harmless, self-healing via deterministic IDs). Full-root clear: explicit `QdrantEntities.delete_by_root_id` + `graph_store.drop_root`.

- [ADR-0014: Entity Targeting Is Additive and Fails Open](../docs/adr/0014-entity-targeting-is-additive-fail-open.md)
  Targeting inserted after detection-committed gate; can only narrow or fall back; no new lifecycle state, response shape, or blocking path.

- [ADR-0015: Per-Cluster Report Freshness and Targeted Summarization](../docs/adr/0015-per-cluster-report-freshness-and-targeted-summarization.md)
  Shift freshness tracking from per-build to per-cluster (`report_build_id` per community row). `reports_committed_build_id` becomes a "full sweep" marker only.

### Implementation decisions (16–21)

- [ADR-0016: Orchestrator Accepts Optional target_clusters Parameter](../docs/adr/0016-orchestrator-accepts-target-clusters-parameter.md)
  Generalize `_run_reports_attempt` with `target_clusters: set[str] | None = None`; single-flight applies unconditionally.

- [ADR-0017: Targeting Uses Stale Join Table; Mapping Is Best-Effort](../docs/adr/0017-targeting-uses-stale-join-table-best-effort.md)
  Join table queried without build_id filter; stale entity→community mappings are acceptable; entity-community relationships are structurally stable.

- [ADR-0018: Single-Flight Coalescing Across All Target Cluster Sets](../docs/adr/0018-single-flight-coalescing-across-all-target-sets.md)
  One lease per root regardless of target set; unrelated concurrent queries serialize rather than requiring per-target-set coordination.

- [ADR-0019: Entity Extraction and Detection Run in Parallel](../docs/adr/0019-entity-extraction-and-detection-run-in-parallel.md)
  Both tasks are independent `asyncio.ensure_future`; detection skips join table if extraction isn't ready; join table appears on the next detection run.

- [ADR-0020: Join Table Rows Cleaned Eagerly; Entity Rows Are Lazy](../docs/adr/0020-join-table-eager-cleanup-entity-rows-lazy.md)
  Detection deletes prior-build join-table rows on commit (bounded size); entity rows are left until root clear (self-healing via deterministic IDs).

- [ADR-0021: Targeting Observability via Structured Logging, Not metrics.db Extension](../docs/adr/0021-targeting-observability-via-structured-logging-not-metrics-db.md)
  metrics.db unchanged (outcome-only); targeting details logged as JSON via `mcp_vectors.search_global.targeting` logger to a file-only handler.
