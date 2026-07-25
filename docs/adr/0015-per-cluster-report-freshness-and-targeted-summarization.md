# Per-Cluster Report Freshness and Targeted Summarization

## Context

ADR-0004 established a report state machine where detection commits community clusters and writes a single per-root `reports_committed_build_id` after generating reports for *all* clusters in one atomic batch. The coverage predicate reads `reports_committed_build_id == committed_build_id` to determine whether reports are ready.

ADRs 0009–0014 introduce entity-driven targeted summarization: at `search_global` time, semantic entity search identifies a *subset* of communities that match the user's request, and only those clusters' reports are summarized (avoiding O(N-communities) batch work on the first query).

A collision arises: if targeted search generates 3 clusters' reports and commits the build, the next query targeting a *different* 3 clusters would see `committed_build_id == reports_committed_build_id` and skip report generation — serving no reports for the newly-targeted clusters. The coverage predicate cannot distinguish "all clusters have fresh reports" from "some clusters have fresh reports."

The `communities` table schema already supports per-cluster report state: each row has `report`, `report_emb_id`, and `report_build_id` columns (graph_store.py:97–103, upsert_communities writes per-row at :1613). The state machine has not yet exploited this capability.

## Decision

Shift report freshness tracking from per-build granularity to per-cluster granularity. The source of truth for "this cluster has a fresh report" becomes each community row's `report_build_id == committed_build_id`, not a single per-root `reports_committed_build_id` field.

**Orchestrator generalization:**
`CommunityOrchestrator._run_reports_attempt` is extended to accept an optional `target_clusters` parameter (None = all clusters, as today; a set of cluster IDs = generate and commit reports only for those clusters). When target clusters are passed:
1. Generate reports only for clusters in the target set.
2. Commit each targeted cluster's report by writing `report`, `report_emb_id`, and `report_build_id` per row (existing pattern).
3. Do **not** set the per-root `reports_committed_build_id` — only the per-row `report_build_id` is written.

The per-root `reports_committed_build_id` is set **only** when a full build (all clusters) is generated and committed. It becomes a soft marker: "a complete sweep has been attempted," useful for observability and list_communities' `incomplete` flag, but not a hard gate on targeted queries.

**Query-time freshness check:**
`search_global` with targeted communities:
1. Resolve targeted community IDs (entity search → join table).
2. **Filter resolved IDs against the current build's existing communities.** Because targeting reads the join table without a `build_id` filter (ADR-0017), a stale mapping row can resolve to a `community_id` that no longer exists in the current build's `communities` table (e.g., after re-clustering). Before any freshness or cap logic, drop resolved community IDs that have no row in the current build's `communities` table. This prevents the freshness check (`report_build_id == committed_build_id`) from treating a nonexistent cluster as "stale" and attempting report generation for a cluster that does not exist. The 30% cap and `total_communities` computation (ADR-0011) operate on this filtered set. If *all* resolved IDs are dropped by this filter, the targeted set is empty and the system takes the zero-match fallback (full summarization, ADR-0011) rather than generating nothing.
3. Fetch the surviving targeted communities' rows.
4. For each targeted community, check `report_build_id == committed_build_id` (per-row freshness).
5. Generate + commit reports (via orchestrator with target set) only for stale targeted clusters.
6. Summarize all targeted clusters (fresh or newly-generated).

A targeted response may have `incomplete: true` (a subset of communities) but the targeted subset itself is fully fresh.

**Fallback behavior:**
If entity targeting returns zero matches or exceeds the 30% community cap (ADR-0011), the system falls back to full community summarization, which uses the original all-clusters path and honors `reports_committed_build_id` as before.

## Considered Options

- **Per-build freshness (status quo, ADR-0004)** — single-flight, atomic, simple to reason about. Breaks under targeted summarization: partial generation leaves the build "committed" but incomplete. Rejected: incompatible with the targeted design goal.
- **Per-cluster freshness with orchestrator generalization** *(chosen)* — matches reporting granularity to targeting granularity; leverages existing per-row schema; preserves the orchestrator's single-flight and TTL-recovery machinery for any cluster subset; full-build path (fallback) continues to work as today.
- **Orchestrator-less, targeted generation in search_global** — `search_global` directly calls community summarization for targeted clusters, bypassing the orchestrator's locking and claim machinery (ADR-0004). Simpler locally but duplicates coordination logic and sacrifices single-flight coalescing.

## Consequences

- The per-root `reports_committed_build_id` is deprecated as a hard gate but retained for observability. Its presence signals whether a full (non-targeted) generation has been attempted; it is consulted only in the full-summarization fallback path and by list_communities.
- Detection's report generation continues to use the all-clusters path, writing per-row `report_build_id` and setting `reports_committed_build_id` atomically. No change to detection's behavior.
- Targeted queries may generate partial-build reports (subset of clusters) and never set `reports_committed_build_id`. This is correct: a partial build is not "committed" in the full sense, but each targeted cluster is fresh.
- `incomplete: true` continues to signal partial community coverage; a targeted response is *by design* incomplete, and callers already handle this state.
- If a targeted query later coincidentally targets a cluster from an earlier partial build, its freshness check (`report_build_id == committed_build_id`) naturally reuses the cached report rather than regenerating.
- The orchestrator's single-flight coalescing and lease/TTL machinery (ADR-0004) now applies to any cluster subset, not just full builds. Multiple concurrent `search_global` calls targeting overlapping clusters are still coalesced by the orchestrator's claim mechanism.
- A repository may end in a state where some clusters have fresh reports and others don't, indefinitely. This is acceptable: targeted queries only consume fresh clusters; a full-summarization fallback (or an explicit full rebuild) can reset the build state if uniform freshness is desired.
- Observability must distinguish targeted vs. full summarization paths (best-effort metrics, consistent with ADR-0005).
