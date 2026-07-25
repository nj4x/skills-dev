# Community-Readiness Deepening — ADR Manifest

Design decisions reached during grilling on 2026-07-23. Candidates A and B from the
mcp-vectors architecture review: close the RAGPipeline seam leaking into server.py, and
replace GraphStore's 16-method report build-state API with 4 atomic domain operations.

## ADRs

- docs/adr/0022-report-build-state-domain-operations.md
- docs/adr/0023-report-build-claim-cas-cross-process.md
- docs/adr/0024-rag-pipeline-community-query-seam.md
- docs/adr/0025-community-query-results-discriminated-union.md

---

## Session Ledger

| Role         | Outcome                  |
|--------------|--------------------------|
| orchestrator | —                        |
| planner      | complete                 |
| critic #1    | revise (major)           |
| critic #2    | revise (major)           |
| critic #3    | revise (major)           |
| critic #4    | revise (major)           |
| critic #5    | revise (minor)           |
| critic #6    | approve (minor)          |

## Critic Review

- **Final verdict:** approve
- **Severity:** minor
- **Iterations used:** 6
- **Approval status:** ✓ Automatically approved by critic. No manual review required.
- **Remaining risks / open questions (optional improvements, not blocking):**
  - ADR-0023 Property 1 covers meta/commit columns; report *payloads* are LLM-generated
    and non-deterministic. Should state report rows are keyed by `(community_id, build_id)`
    and written idempotently (upsert) so a duplicate build overwrites rather than
    interleaves.
  - ADR-0022 discard-and-recreate also drops the entity graph, not just
    communities/reports — true migration cost may include entity re-extraction (possibly
    LLM calls), materially more than "re-detection" implies.
  - Absolute-epoch leases assume a single-host coherent clock; unstated assumption, would
    break under a networked/multi-host `GRAPH_DB_DIR`.
  - ADR-0024 leaves `search_global` on a separate readiness check — two parallel readiness
    protocols; tracked follow-up to fold into a third pipeline method.
