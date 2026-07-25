# Parallel critic reviews by lens concern group with unanimous approval

The critic coordinator spawns 4–5 parallel sub-agents each owning a distinct lens concern group. The final verdict requires unanimous approval; severity is the maximum across all sub-agents.

## Context

The current critic evaluates 10 adversarial lenses sequentially in a single agent call. Parallelising requires partitioning these lenses across sub-agents and defining a merge rule.

Two partitioning strategies were considered:
- **By artifact slice**: each sub-agent reviews a section or ADR file. Requires pre-partitioning the plan and risks inconsistent lens coverage per section.
- **By concern domain**: each sub-agent owns a coherent lens grouping (completeness, consistency, robustness, execution). Every sub-agent reviews the whole artifact but through its own lens cluster. Coverage is always complete; groupings are predictable.

Three merge rules were considered:
- **Unanimous**: approve only if all sub-agents approve. Any `revise` → final `revise`.
- **Majority**: approve if ≥N/2 sub-agents approve.
- **Weighted**: "must-have" lens groups must approve; "nice-to-have" may fail.

## Decision

**Partitioning**: by concern domain. The groups are:

For implementation plans (5 groups):
- A — Completeness & Scope (lenses: scope creep, simplicity)
- B — Consistency & Coherence (assumptions, contradictions, trade-off justification)
- C — Edge Cases & Robustness (missing edge cases, failure modes & rollback)
- D — Execution & Ordering (ordering/sequencing, testability & verification)
- E — Operational Concerns (ops: logging, monitoring, migration, rollout)

For design reviews / ADRs (4 groups): same as above, omitting Group E (lenses 3, 4, 7, 9 are plan-only). Group C condenses to edge cases only.

Each sub-agent receives a tailored prompt listing only its 2–3 lenses and instructed to ignore the rest.

**Merge rule**: unanimous. Final verdict is `approve` only if all sub-agents return `approve`. Final severity is the maximum across all sub-agents (major > minor > none). All sub-agents' `top_issues` and `suggested_fixes` arrays are concatenated and deduplicated.

## Consequences

- Coverage is guaranteed: every lens group is always evaluated, not just the lenses the single critic happened to emphasise.
- Unanimous rule is conservative — a single sub-agent that finds a real issue blocks approval. If this proves too strict in practice (irrelevant lens groups blocking on noise), the fix is tighter prompt scoping before loosening the merge rule.
- Five parallel sub-agents replace one serial critic agent. Turnaround time should be similar or faster; context insulation at the coordinator level is the primary win.
- Each sub-agent prompt must be maintained separately; adding or removing a lens requires updating the corresponding group prompt.
