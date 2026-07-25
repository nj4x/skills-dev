# Entity Targeting Uses Stale Join Table; Mapping Is Best-Effort

## Context

The `entity_community` join table (ADR-0010) maps entity IDs to community IDs scoped by `(root_id, build_id)`. Detection writes a new build's rows when it commits; each row records the `build_id` of the detection run that produced it.

At `search_global` time, the join table lookup maps semantically-matched entities to community IDs. A question arises: should targeting only use rows from the *current* `committed_build_id`, or use whatever rows are available regardless of `build_id`?

**Relationship to ADR-0020 (eager join-table cleanup).** ADR-0020 deletes all join-table rows whose `build_id != current` at each detection commit (`DELETE FROM entity_community WHERE root_id = ? AND build_id != ?`). Therefore, in steady state, only current-build rows exist and a `build_id` filter would be redundant. This ADR does **not** rely on cross-build stale rows persisting across completed builds — under ADR-0020 they do not. The decision to omit the `build_id` filter is deliberately about two narrower situations: (1) the window *during an in-progress rebuild*, after the prior build's rows exist but before the new build has committed and run its cleanup DELETE, where the omitted filter keeps targeting available against the prior mapping; and (2) avoiding a hard coupling between targeting and the exact current `committed_build_id`, so targeting never enters a "blocked until detection re-runs" state. In both cases the mapping used may be slightly out of date, which is why targeting is treated as best-effort and correctness is enforced downstream (ADR-0015 freshness checks, ADR-0011 cap/fallback).

## Decision

Entity targeting queries the join table without a `build_id` filter. Any join-table row for the target `root_id` contributes community candidates, regardless of which detection build wrote it.

```sql
SELECT DISTINCT community_id
FROM entity_community
WHERE entity_id IN (…) AND root_id = ?
-- No build_id filter
```

## Considered Options

- **Use stale join table; no build_id filter** *(chosen)* — maximizes targeting uptime; entity-to-community relationships are structurally stable across detection builds; any mapping produces useful community candidates. Note that under ADR-0020's eager cleanup, only current-build rows normally exist; the true benefit of omitting the filter is availability during an in-progress rebuild (pre-commit window) and avoiding a hard dependency on the current `committed_build_id`, not reliance on long-lived cross-build rows.
- **Require current build_id; fall back to full summarization if stale** — ensures targeting is aligned with the current cluster structure; blocks targeting until detection re-runs with fresh join-table rows; reintroduces latency when detection lags.
- **Use stale table with conservative 50% community cap** — allows targeting but caps the result set more aggressively when mapping is uncertain. Rejected: the 30% cap (ADR-0011) already provides the safety valve; a second, stricter cap for staleness adds a threshold without clear benefit.

## Consequences

- Targeting is always available after the first detection build, regardless of whether detection has re-run. There is no "stale targeting" blocking state.
- If detection re-clustered entities significantly (e.g., a major refactor), targeting may point at communities that have changed. The 30% cap and zero-match fallback (ADR-0011) bound the blast radius.
- A stale mapping (from an in-progress rebuild's pre-commit window) can resolve to a `community_id` absent from the current build's `communities` table. ADR-0015's targeting path filters resolved IDs against the current build's existing communities before freshness/cap checks and drops any dangling IDs, so this never triggers report generation for a nonexistent cluster. In the partial-dangle case — where some resolved IDs are valid and some are dangling — the filter drops only the dangling IDs; targeting proceeds on the surviving subset (subject to the 30% cap and zero-match fallback). This is correct: a partial resolution is better than a full fallback.
- The targeting log should record the detected join-table build_id(s) to help operators diagnose targeting accuracy ("targeted using mapping from build N, current build is M").
- This is consistent with ADR-0014's fail-open principle: targeting produces a best-effort narrowing; correctness is guaranteed by community report freshness checks (ADR-0015), not by join-table currency.
