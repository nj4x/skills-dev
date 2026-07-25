# Extract CommunityOrchestrator to own the full community-rebuild lifecycle

## Status

proposed

## Context

`RAGPipeline`'s community-rebuild state machine is smeared across `_schedule_community_rebuild`, `_on_community_task_done`, `_rebuild_communities` (plus a `finish_failure` closure), and five instance dicts: `_community_tasks`, `_community_reschedule_flags`, `_community_retry_attempts`, `_collection_recovery_attempts`, and `_graph_stats`. Understanding a single rebuild requires tracing calls across three files (`rag.py`, `graph_store.py`, `qdrant.py`) while reconciling `graph_version`, `committed_build_id`, and `build_id` throughout. The module has near-zero locality and high test coupling — six-plus tests reach directly into these internals.

Measured against the deep-module vocabulary: the community-rebuild *implementation* is large, but the *interface* a caller needs to trigger a rebuild is just a `root_id`. That gap is the signal for a deepening.

## Decision

Extract a `CommunityOrchestrator` module (`vectors/community_orchestrator.py`) that owns the **full** background lifecycle: scheduling, live-task tracking, reschedule coalescing, retry, and the durable claim/complete/fail handshake.

Interface (the whole external surface):

- `schedule(root_id)` — fire-and-forget, idempotent, coalescing. The primary entry point.
- `schedule_dirty_roots()` — startup sweep, replacing the loop in `RAGPipeline.initialize()`.
- Construction: `CommunityOrchestrator(graph_store, communities, lm_client, llm_client, progress_callback)`.

The orchestrator's internal single-attempt logic returns a `CommunityBuildResult`; the pipeline records stats from that result. Live phase transitions (`detecting` → `reporting` → `embedding` → `ready`/`failed`) are surfaced via an injected `progress_callback(root_id, phase)` so the orchestrator stays stats-oblivious while phase-level observability is preserved.

## Considered Options

- **Move only the single-attempt logic (`_rebuild_communities`).** Rejected: the complexity lives in the *coordination* (claim, task-tracking, reschedule, version reconciliation), so a single-attempt extraction leaves the state machine smeared — a shallow win that fails the deletion test.
- **Orchestrator owns construction of its dependencies.** Rejected: `GraphStore` and `QdrantCommunities` serve non-rebuild purposes elsewhere in the pipeline (entity extraction writes to the graph; `search_global` reads communities), so the pipeline constructs and injects them; the orchestrator gets references to the same instances.
- **Orchestrator owns the stats dict.** Rejected: stats are a cross-root concern the pipeline already exposes via `get_graph_stats`; the orchestrator returning a result plus emitting a progress callback keeps the dict at the pipeline level without a callback-up-to-pipeline dependency.

## Consequences

- All retry logic, version reconciliation, and durable-lease CAS concentrate in one file — locality restored.
- Six-plus tests that poke `_schedule_community_rebuild` / `_community_tasks` / `_graph_stats` directly must redirect to the orchestrator (optionally softened by thin pipeline-level delegators).
- `RAGPipeline` shrinks ~200 lines; the community-rebuild path becomes one seam, one adapter.
- Initialization ordering must be respected: `lm_client.initialize()` and `_communities.initialize()` must complete before the orchestrator is constructed and used.
