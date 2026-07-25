# Entity Targeting Is Strictly Additive and Fails Open

## Context

Entity extraction and community detection both run as background tasks after indexing (`asyncio.ensure_future`, `rag.py:553`). On a freshly-indexed root the ordering is:

1. File indexed — chunks searchable immediately.
2. Background: entity extraction → entities in SQLite → entity embeddings in `mcp_vectors_entities`.
3. Background: detection → `entity_community` join table populated (ADR-0010).

`search_global` can be called at any point during this sequence. The new entity-targeting step (semantic entity search → community selection) has no inputs until steps 2 and 3 complete. A design is needed for what targeting does when its inputs are partially or fully absent, without regressing the existing `mode="rebuilding"` behavior.

## Decision

The entity-targeting step is inserted into `search_global` **after** the existing detection-committed gate and **before** full report generation. It can only narrow the community set or fall back; it never blocks, errors, or introduces a new lifecycle state.

Concretely:
- If detection has not committed (`is_dirty or not committed_build_id`), the **existing** `mode="rebuilding"` + vector fallback fires first (`rag.py:1540`). Targeting is never reached, so the `entity_community` join table is guaranteed populated whenever targeting runs.
- If the entities collection is empty for the root, or entity search returns zero matches, targeting falls back to **full community summarization** — identical to the Q5/ADR-0011 zero-match and 30%-cap fallbacks.
- Targeting therefore has exactly two outcomes: a narrowed community set, or the pre-existing full-summarization behavior.

## Considered Options

- **Additive, fail-open, no new mode** *(chosen)* — targeting narrows or falls back; response shape and lifecycle states are unchanged; callers need no awareness of targeting.
- **Distinct `mode` signal for targeted vs. full** — lets callers distinguish a targeted response from a full one. Rejected as the primary contract: it leaks an internal optimization into the public response shape and invites callers to branch on it. Observability is better served by a non-blocking metrics field than by a caller-facing mode.
- **Block until entity embeddings are ready** — introduces a new "rebuilding" state gated on entity extraction. Rejected: adds latency and a new blocking path, directly contradicting the first-query-latency goal.

## Consequences

- No new lifecycle state, error code, or response-shape change is introduced by entity targeting. Existing callers of `search_global` are unaffected.
- The optimization is invisible on the happy path except for reduced latency. Whether a given call was targeted or full can be recorded as a best-effort metrics field (consistent with ADR-0005 metrics), not surfaced as a `mode`.
- Because targeting runs only after the detection-committed gate, the join table is always available when targeting executes — no intra-targeting "not ready" branch is needed.
- The `incomplete` flag continues to signal partial community coverage as before; a targeted response naturally sets `incomplete: true` when it summarizes a subset.
