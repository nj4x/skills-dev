# Split Community Detection from Report Generation (Lazy Reports)

Community report generation (`generate_all_reports`) costs one LLM call per detected cluster and was triggered eagerly after every file index — including roots whose community tools (`search_global`, `list_communities`, `get_community_report`) are never called. Community *detection* (`detect_communities`) is a pure graph algorithm with no LLM cost. The waste is entirely in reports generated for communities nobody reads.

We decided to split the two phases into independent orchestration workflows within `CommunityOrchestrator`: detection stays eager and cheap (fired after graph mutations, as today), and report generation becomes consumer-pull only, triggered the first time `search_global` or `get_community_report` requests report text or embeddings. Detection and reports each have their own durable claim/complete/fail lifecycle with separate state slots in the graph store.

## Considered Options

- **Defer the whole rebuild** — simplest, but `list_communities` structure also becomes unavailable until first request.
- **Split detection/reporting** *(chosen)* — detection stays instant; only the expensive phase defers.
- **Keep eager, throttle harder** — doesn't fix the root problem (wasted work when tools are never called).

## Consequences

- First consumer call after indexing returns `mode="rebuilding"` + vector-search fallback while reports generate. Subsequent calls hit the cache.
- Report failures are isolated; detection remains durable and is not retried on report failure. Reports retry naturally on the next consumer request.
- Zero LLM spend when community tools are never called for a given root.

## Implementation Details

**Two-phase lifecycle within CommunityOrchestrator:**
- `schedule_detection(root_id)` is called by indexing sites and startup. It runs detection only: `detect_communities`, publish structure to the graph store, mark detection complete. No reports generated.
- `schedule_reports(root_id)` is called by consumers (`search_global`, `get_community_report`) when they need report text or embeddings. It runs report generation only: `generate_all_reports`, embed and publish reports, mark reports complete. Single-flight coalescing per root: concurrent calls to `schedule_reports` for the same root coalesce to one generation attempt.

**Report/detection staleness coherence:**
Reports are tagged with the detection `build_id` they were generated for. The authoritative staleness check is `report_build_id == communities_committed_build_id`; only reports matching the current build are fresh. When detection commits a new build (cluster set has changed), it atomically sets `reports_dirty=1` as an advisory hint (consumers can fast-path `mode="rebuilding"` without fetching all reports). Old reports for previous builds are kept in storage but are filtered by the build_id check and do not satisfy coverage requirements. The `reports_dirty` flag is advisory only; if it races and clears while a build_id change is in-flight, the next consumer's build_id check catches the stale reports and re-triggers generation.

**Failure handling for partial reports:**
Report generation per cluster has bounded retry with exponential backoff; after max attempts, a cluster's report slot is marked failed-permanently. A permanently-failed slot automatically resets after a configurable base TTL (default: 24 hours). On each TTL reset, the cluster re-enters the pending/retrying state; if the retry also fails, the next TTL doubles (24h → 48h → 96h, capped at 30 days). This bounded oscillation is expected and documented. The base TTL is fixed-configurable; the doubling is a separate per-slot backoff multiplier applied on consecutive failures.
- `search_global`: returns `mode="rebuilding"` while any current-build cluster is pending or retrying. The coverage predicate is: `incomplete: false` only when every current-build cluster has a committed report embedding; `incomplete: true` otherwise. Once all generation work is settled (every cluster is either committed or permanently-failed), `search_global` returns available embeddings with `incomplete: true` if any clusters failed. If all current-build clusters are permanently-failed with no available embeddings, `search_global` falls back to vector-search results with `incomplete: true` (matching the rebuilding-state fallback). This allows graceful degradation rather than indefinite blocking or empty results.
- `list_communities` (which needs only cluster structure) returns immediately with detected structure, regardless of report generation state.
- `get_community_report` (which needs one specific report) returns `mode="rebuilding"` while that cluster's report is pending or retrying; once committed or failed, it returns the report (or marks permanent failure) and is visible to the caller.

**Graph store schema:** Two independent state slots are added to the `meta` table:
- Existing `communities_version`, `communities_dirty`, `communities_committed_build_id`, `communities_claimed_build_id`, `communities_claim_lease_seconds` track detection state (unchanged).
- New `reports_version`, `reports_dirty`, `reports_committed_build_id`, `reports_claimed_build_id`, `reports_claim_lease_seconds` track report-generation state. Reports include a `report_build_id` field linking each report to its source detection build.

**Detection/reports ordering:**
When detection commits a new build, it atomically sets `reports_dirty=1`. If `schedule_reports` is in-flight for the old build, it completes and publishes reports (with old `report_build_id`). The next consumer request sees `reports_dirty=1` and calls `schedule_reports` again, triggering fresh generation against the new cluster set. No task cancellation or orchestrator coupling needed; staleness is managed via the graph-store flag.

**Call-site changes:**
- Four indexing/graph-mutation call sites now call `schedule_detection`:
  - Background entity extraction (`rag.py:476`)
  - File-entity cleanup (`rag.py:1043`)
  - Foreground entity-extraction endpoint (`rag.py:1261`)
  - Startup sweep (`rag.py:254`): `schedule_dirty_roots()` internally calls `schedule_detection` for each dirty root (no signature change)
- Two consumer call sites in `search_global` now call `schedule_reports`:
  - When dirty or no committed generation (`rag.py:1367`)
  - When collection is missing (`rag.py:1392`)

**Metrics and observability:**
For the full list of recorded fields, management CLI, and efficacy measurement strategy, see ADR-0005 "Token cost trade-off and efficacy metric" section. Metrics recording (tool invocations, timing, outcomes) is best-effort and non-blocking; a metrics write failure never blocks a tool call or report generation.
