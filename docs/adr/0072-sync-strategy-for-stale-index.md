---
lineage-rules: exempt
---

# ADR-0072: Stale Index Detection and Sync Strategy

**Status:** Decided  
**Date:** 2026-09-03  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

Index staleness is detected by checking if Qdrant has any chunks for a root. A 4-week-old index stays in Qdrant with no auto-refresh. Calling `index_codebase()` on a stale root returns `indexed=false` and declines to re-index unless `force=true`.

Without automatic incremental re-indexing, users must either:
1. Call `index_codebase(force=true)` to wipe and rebuild everything (slow, rebeds all files).
2. Call `sync_directory()` to reconcile against disk (fast, only re-embeds changed files).

## Decision

No automatic re-indexing on stale detection. Instead:

1. **Clear status messaging:** `index_codebase()` result includes a field `stale_since` (ISO 8601 timestamp) if the index is older than a threshold (default 7 days, configurable via `STALE_INDEX_THRESHOLD_DAYS`). This surfaces staleness to the caller.

**Staleness threshold basis:** 7-day default chosen as a common artifact refresh window; users can tune `STALE_INDEX_THRESHOLD_DAYS` env var to match their codebase churn rate.

2. **Recommendation in error:** If `force=false` and the index is stale, the result message suggests: *"Index is stale (last updated 4 weeks ago). Use `force=true` to re-index or call `sync_directory()` to reconcile against disk (faster)."*

3. **User choice:** Caller decides: `force=true` for guaranteed-fresh index, or `sync_directory()` for incremental updates.

4. **No auto-sync:** No auto-sync or background refresh jobs; incremental updates are user-driven via `sync_directory()` on manual trigger only.

## Rationale

- **Simplicity:** No new background jobs or scheduled tasks.
- **Transparency:** User sees the age of the index and can decide when to refresh.
- **Flexibility:** `sync_directory()` is fast for large repos; `force=true` is slow but guaranteed.
- **Consistency:** Stale detection doesn't change behavior; it only improves messaging and observability.

## Consequences

- **Prerequisite:** Staleness detection requires `indexed_at` timestamps in Qdrant chunk metadata. This field is already wired in chunk payloads (vectors/metadata.py, build_chunk_payload_v2); the oldest timestamp per root is retrieved via metadata query to Qdrant.
- Users must actively manage index freshness. A 4-week-old index won't auto-refresh; search results reflect the old state.
- Large repos benefit from explicit `sync_directory()` calls instead of full re-indexing.
- Staleness threshold is configurable; users can tune it to their refresh cadence.
- If indexed_at is absent from chunk metadata, the root is treated as stale (conservative default), and the `stale_since` field is populated with the current timestamp.
