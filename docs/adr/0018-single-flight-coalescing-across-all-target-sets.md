# Single-Flight Coalescing Applies Across All Target Cluster Sets

## Context

ADR-0004 established a single-flight claim/lease mechanism for report generation: one in-flight generation batch per root at a time, coordinated by a lease in the community orchestrator. ADR-0016 generalizes the orchestrator to accept an optional `target_clusters` set.

With targeted summarization, multiple concurrent `search_global` calls may each supply a different `target_clusters` set (e.g., call A targets {auth, users}, call B targets {database, caching}). A question arises: should the single-flight lease gate on any in-flight generation, or should it be scoped per target set so that unrelated target sets can run concurrently?

## Decision

The single-flight claim/lease applies across all generation work for a root, regardless of the target cluster set. If any report generation is in flight (targeted or full), new generation requests for the same root wait for the in-flight batch to complete before starting.

## Considered Options

- **Coalesce across all targets** *(chosen)* — one lease per root; simplest; preserves ADR-0004's coordination model without modification; TTL-recovery applies uniformly.
- **Coalesce per target set** — concurrent unrelated queries don't block each other; requires tracking multiple in-flight states (one per target set); overlapping target sets risk generating the same cluster twice; significantly more complex.
- **Merge overlapping target sets on-the-fly** — prevents duplicate work on overlaps; doesn't block unrelated queries; most complex; requires expanding pending requests dynamically while a batch is in flight.

## Consequences

- Two concurrent `search_global` calls targeting disjoint cluster sets will serialize: the second waits for the first to finish, then runs its own generation. On fast systems this is imperceptible; on slow LLM clients it may add latency.
- The second call benefits from per-cluster freshness (ADR-0015): clusters already committed by the first call are skipped. Only the second call's targeted clusters that are genuinely stale are generated.
- If cross-target blocking becomes observable as a user-facing problem, per-target coalescing can be introduced without changing the public `search_global` interface — it is an orchestrator-internal change.
- ADR-0004's TTL-recovery (lease expiry on hung batches) continues to work: it is per-root, so it correctly recovers from any stalled generation regardless of target set.
