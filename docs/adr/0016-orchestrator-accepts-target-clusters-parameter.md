# Orchestrator Accepts Optional target_clusters Parameter

## Context

ADR-0004 defines `CommunityOrchestrator._run_reports_attempt` as an all-clusters operation: it calls `generate_all_reports(clusters, ...)` over every cluster in a detection snapshot, then sets a single per-root `reports_committed_build_id` atomically. ADR-0015 introduces per-cluster report freshness and targeted summarization: `search_global` should be able to generate reports for a subset of clusters rather than all.

Three approaches were considered for exposing subset generation through the orchestrator: (A) add an optional `target_clusters` parameter to the existing method, (B) split into two separate methods preserving the original's all-or-nothing contract, or (C) extract a lower-level "generate these clusters" function and make the orchestrator delegate to it.

## Decision

Add an optional `target_clusters: set[str] | None = None` parameter to `_run_reports_attempt`. When `None` (the default), behavior is unchanged: all clusters are generated and `reports_committed_build_id` is set atomically. When a non-empty set is passed, only those clusters are generated; each cluster's report is committed per-row (via `report_build_id`); `reports_committed_build_id` is NOT set (it remains a "full sweep" marker only).

The orchestrator's single-flight claim/lease/TTL-recovery machinery (ADR-0004) applies unconditionally, regardless of whether the call is targeted or full.

## Considered Options

- **Optional `target_clusters` parameter** *(chosen)* — one method, one entry point; single-flight applies to all generation work; no logic duplication.
- **Two separate methods** — preserves the original method's contract; adds logic duplication and two entry points to maintain; targeted path could inadvertently bypass the orchestrator's lease machinery if a caller calls the wrong method.
- **Delegate to lower-level generator** — adds abstraction layers; the orchestrator's coordination is more modular but split across layers; harder to reason about who owns the claim.

## Consequences

- Detection continues to call `_run_reports_attempt(root_id, snapshot, llm_client)` (no target_clusters) — behavior unchanged.
- `search_global` calls `_run_reports_attempt(root_id, snapshot, llm_client, target_clusters={...})` — generates and commits only targeted clusters.
- `reports_committed_build_id` is only set when `target_clusters is None`, preserving its meaning as "a full sweep has been completed."
- Multiple concurrent `search_global` calls coalesce via the same single-flight lease regardless of their target sets (ADR-0018 elaborates on this).
