# Critic groups: shared three-group core plus artifact-specific groups

(Filename and any "fifth group" phrasing retain the historical `fifth-group` slug; the accurate framing is the title above. Specs and tickets carry a **fourth** group in slot D, not a fifth — only `plan` reaches five groups. See the roster below. The stale slug is left in place rather than renaming the file and rewriting the manifest entry.)

The critic's parallel sub-agent review is built from a **shared three-group core** plus **artifact-specific groups**. The core (A — Completeness & Scope, B — Consistency & Coherence, C — Edge Cases & Robustness) applies to every artifact type. The artifact-specific groups differ by type, and so does the **total group count**. This ADR fixes the roster and the count; group selection is keyed on the detected `artifact_type` (ADR-0037).

**Status:** the plan and design-review rosters match the current `critic/SKILL.md`; the spec and tickets rosters are new and land with the ADR-0037 detection change.

## Concrete roster per artifact type

| artifact_type | Groups | Count |
|---|---|---|
| `plan` | A, B, C, **D — Execution & Ordering**, **E — Operational Concerns** | 5 |
| `design-review` | A, B, C | 3 |
| `spec` | A, B, C, **D — Requirement Traceability** | 4 |
| `tickets` | A, B, C, **D — Slice Boundaries** | 4 |

Notes:

- **Group E (Operational Concerns) is plan-only.** It is **dropped** for `spec`, `tickets`, and `design-review` — a spec document and a ticket list have no operational surface (logging, monitoring, rollout) to review.
- **Group D (Execution & Ordering) is plan-only** as originally defined; `spec` and `tickets` replace slot D with their own artifact-specific lens rather than reusing execution ordering.
- **`design-review`** keeps the existing 3-group behaviour of the SKILL (core only; both D and E gated out). ADR-0033's "4 groups" description is superseded by this table.

Artifact-specific group lenses:

- **spec / D — Requirement Traceability (internal-consistency only)**: are the requirement IDs the spec references used **consistently within the spec itself**? Every user story / implementation decision that cites an ID (inline `(REQ-…)` tags) must resolve against the spec's own `Requirements:` mapping; the mapping must not cite IDs that no story covers, and no story may cite an ID absent from the mapping. **Existence of a REQ-ID in the external requirements corpus is out of scope** — only the draft spec file is passed to critic (ADR-0038), so the group cannot verify that a REQ-ID actually exists upstream. The lens is bounded to *self-consistency of the IDs the spec names*, not corpus membership.
- **tickets / D — Slice Boundaries**: does each slice cut a complete vertical path (schema→API→UI→tests)? Is each slice demoable and sized to one fresh context window? Is the blocking-edge topology acyclic, free of dangling `Blocked by` references, and correctly ordered (prefactors first)?

The critic coordinator spawns `count` sub-agents (one per group in the row for the detected `artifact_type`) in a single message.

## Implementation note: generalize the binary toggle to a 4-way switch

`critic/SKILL.md` today selects groups with a **binary `is_design_review` toggle** and a **hardcoded spawn-count string**. Realizing this ADR requires replacing both with a **4-way dispatch keyed on `artifact_type`** (`plan` → 5, `design-review` → 3, `spec` → 4, `tickets` → 4), selecting the group roster and the spawn count from the table above.

The current SKILL also carries a **pre-existing spawn-count/group-count mismatch**: its design-review path states a spawn count of **4** while defining only **3 groups** (core A/B/C, with D and E gated out). This mismatch must be **fixed as part of this work** — design-review resolves to **3** groups and **3** spawned sub-agents, consistent with the roster table (this also supersedes ADR-0033's "4 groups" description). The 4-way switch must derive the spawn count from the roster, not from a stale literal, so the count and the number of spawned agents can never again diverge.

## Considered Options

- **Reuse all 5 plan lenses for specs and tickets**: Execution & Ordering and Operational Concerns would fire on specs and tickets, producing irrelevant findings and missing the relevant ones (traceability, slice boundaries).
- **Fully fork all groups per artifact type**: four independent codepaths to maintain; the three shared core lenses would drift out of sync.
- **A single "fifth group" for every non-plan type**: rejected — the artifact-specific concern differs by type (traceability vs. slice boundaries) and the count differs too (spec/tickets = 4, plan = 5, design-review = 3), so a uniform "fifth group" framing is inaccurate.
