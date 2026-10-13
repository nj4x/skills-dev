---
name: setup-lineage
description: Retrofit an existing repo with lineage frontmatter and inline source-reference fields across the FS→SRS→ADR→Spec→Ticket chain. Standalone skill — not part of setup-skills.
---

## Requirements boundary

FS records product outcomes, capabilities, lifecycle behavior, and material safety constraints. SRS records the system capability, lifecycle, and safety contracts that satisfy FS. Neither defines invocation mechanisms: endpoints, transports, topics, request/response schemas, storage representations, providers, libraries, modules, or deployment topology.

An external mechanism mandated by product, regulation, or a partner is an FS/SRS constraint only when stated through its required observable effect; its realization remains an ADR decision. API contracts, use-case sequences, and data realization belong in the ADR that selects or changes them. Include the relevant ADR section only when that mechanism is decided or changed.

New or materially edited FS/SRS items must meet this boundary. Rewrite mechanism-bound source material to its outcome or contract, then route the mechanism to an ADR. Preserve unchanged legacy detail, but report it as drift. Legacy companion documents are read-only projections: validate their cited SRS IDs, do not add obligations to them, and do not create new companions.

All lineage-enabled skills must consult this section when authoring, refining, linking, or auditing requirements.

### Granularity

The three layers answer different questions: FS says what the product does for its users, SRS says what the system guarantees at its boundary, and an ADR says how the system does it.

**FS item** — one observable product outcome or business rule, in domain words.

- A product acceptance scenario verifies it without knowledge of system internals.
- It covers roles and permissions, business rules with their parameters (for example "nesting limited to 2 levels"), lifecycle states, user-visible behavior including UI, and material safety, regulatory, or partner constraints stated as observable effects.
- It does not split an outcome into steps, error branches, or attribute lists.
- Quality expectations appear as user-perceived outcomes (for example "search results appear without noticeable delay"); SRS makes them measurable.

**SRS item** — one system-level guarantee between an actor (or external system) and the system. No UI.

- A system-level test with defined preconditions and expected results verifies it.
- It refines FS with precision, not technology: preconditions, postconditions, invariants, failure and edge behavior (rejected input, denied access, conflicting change), authorization per actor, entities and attributes in business terms, observable events, and measurable non-functional targets (metric, threshold, unit, condition).
- It traces to at least one FS item; one FS item may yield several SRS items.
- When an SRS item adds product intent that no FS item states, add or amend the FS item first.

**Placement test** — what a user or the business observes goes to FS; what the system must always guarantee, including failure cases, goes to SRS; how it is achieved goes to an ADR.

## Requirements corpus lookup

Every lineage-enabled skill finds and checks FS/SRS requirement IDs this way. This section covers reading only; where a skill writes requirements is unchanged.

1. **Read the block.** Open the project's `docs/agents/domain.md` and find its `## Requirements corpus` section. Each key is one `- <key>: <value>` line; read the keys by name:
   - `path` — the corpus root.
   - `id-pattern` — the shape of a corpus ID, including how it marks an FS item versus an SRS item.
   - `resolver` — a command that takes one ID, new or legacy, and prints where it lives. Exit 0: found. Exit 1: unknown ID. Exit 2: the corpus cannot be loaded.
   - `fallback` — how to read an item without the resolver.
   - `legacy-index`, `legacy-ids`, `families` — retired and routed IDs, the frozen legacy-ID universe, the family table.
   - `legacy-corpus` — the older corpus that still holds unmigrated items, while it exists.
2. **Block present.** The corpus is every file under `path`, plus `legacy-corpus` while that directory exists. FS and SRS items can share a file; tell them apart by `id-pattern`, and a legacy ID by the legacy file that holds it. Check that an ID exists by running `resolver`. When the resolver cannot run (missing toolchain), use `fallback` for an ID that matches `id-pattern`, and for any other ID search `legacy-index`, then `legacy-corpus`.
3. **Block absent.** The corpus is `.data/requirements/`: FS documents `*-FS-*.md`, SRS documents `*-SRS-*.md`. An ID exists when any `.md` file there contains it: IDs added by amendment files (for example `SRS-AMENDMENT-*.md`) live only there.
4. **Neither found.** With no block and no `.data/requirements/`, the project has no requirements corpus. A lookup that only reads reports this and continues; a guard that protects requirement IDs refuses.

## Phase 1 — Auto-Inference (FS→SRS only)

1. Find the FS items through [Requirements corpus lookup](#requirements-corpus-lookup). For each, extract requirement IDs and one-line summaries.
2. Find the SRS items the same way. For each, extract requirement IDs and one-line summaries.
3. For each SRS item without an existing `**Source FS**:` field, semantically match it to likely FS source(s).
4. Classify each match into a confidence tier:
   - **High** (≥85% match): include in batch-approval list (pre-checked; user may uncheck before confirming)
   - **Medium** (50–84%): present individually for approval
   - **Low** (<50%) or no match: defer to Phase 2

5. Present the approval UI and wait for user confirmation before making any writes:
   - High-confidence matches: one batch-approval list; user unchecks to exclude
   - Medium-confidence matches: one by one, each requires explicit accept/reject

> **Scope limit**: ADR→SRS, Spec→ADR, and Ticket→Spec links lack reliable automated inference signal — resolve all in Phase 2.

---

## Phase 2 — Grilling (Gap Resolution)

### Lineage level model

- **FS** defines high-level product requirements: user/system outcomes and material constraints.
- **SRS** defines the system capability, lifecycle, and safety contracts that satisfy FS. Legacy companion documents project an SRS and cite its requirement IDs.
- **ADR** records lower-level architectural or implementation decisions that realize an existing SRS contract; an ADR does not need a one-to-one SRS requirement when a broader interface or invariant governs it.

Before treating an ADR as unanchored, search the SRS and companions marked `lineage-rules: companion of SRS` for the governing capability, interface, entity, workflow, or invariant. A companion may locate a cited SRS requirement ID but cannot itself anchor the ADR. Anchor to that validated SRS ID when it covers the ADR's behavior, even if the ADR selects the concrete schema, library, validation method, storage shape, or provider translation.

Only when no existing SRS requirement ID covers the ADR's behavior, grill a proposed new SRS requirement. If that requirement has no defensible product outcome or constraint in FS, grill and define a new FS requirement first. Do not create a duplicate SRS requirement merely because the ADR is more detailed than its existing system contract.

Work through each artifact type that has unresolved chain links. Ask the user for each missing anchor:

| Artifact | Missing field | Question to ask |
|----------|---------------|-----------------|
| SRS item | `**Source FS**:` (no match from Phase 1) | "Which FS requirement does `<SRS-ID>` trace to? Options: existing ID / create new FS item / skip" |
| ADR | `**Source SRS**:` | "Which SRS requirement does ADR `<filename>` trace to? Options: existing SRS ID / create new SRS item / skip" |
| Spec | `**Source ADR**:` | "Which ADR(s) does this spec derive from? Options: existing path(s) under `docs/adr/` / create new ADR / skip" |
| Ticket | `**Spec**:` and/or `**Source ADR**:` | "Does this ticket trace to a spec slug, an ADR, or both? Options: spec slug / ADR path / both / skip" |

For "create new FS item" responses: draft the requirement in EARS format, get user approval, write to the relevant FS document, then use the new ID as the anchor.

Skip items the user explicitly skips — record them in the lineage report as "user-skipped / unresolved."

Phase 2 is complete when every artifact either has a confirmed anchor or is explicitly marked user-skipped.

---

## Phase 3 — Writing

After all approvals and gap-resolution answers are collected, write everything in one pass:

### 3.1 Frontmatter

Write `lineage-rules` frontmatter to all artifacts per ADR-0056:

| Artifact type | `artifact-type` | `lineage-rules` value |
|---|---|---|
| FS | `fs` | `root` |
| SRS | `srs` | structured rule list referencing FS anchor |
| ADR | `adr` | structured rule list referencing SRS anchor |
| Spec | `spec` | structured rule list referencing ADR anchor |
| Ticket (spec-linked) | `ticket` | structured rule list referencing Spec |
| Ticket (spec-linked + ADR) | `ticket` | structured rule list referencing both Spec and ADR |
| Ticket (adr-direct) | `ticket` (+ `ticket-subtype: adr-direct`) | structured rule list referencing ADR |
| Legacy companion | appropriate type | preserve `lineage-rules: companion of SRS`; do not write new companions |

### 3.2 Inline source-reference fields

Write `**Source X**:` fields to each artifact body immediately after the frontmatter block:

- FS: no source field (root)
- SRS: `**Source FS**: <FS-ID>`
- ADR: `**Source SRS**: <SRS-ID>`
- Spec: `**Source ADR**: docs/adr/<filename>.md`
- Ticket (spec-linked): `**Spec**: <feature-slug>` (may also carry `**Source ADR**:` if user supplied both)
- Ticket (adr-direct): `**Source ADR**: docs/adr/<filename>.md`
- Legacy companion: validate existing `**Source SRS**:` IDs; do not overwrite or add

### 3.3 Lineage report

Write a report to `.data/lineage-retrofit-report.md` with three sections:

```markdown
# Lineage Retrofit Report

## Matched and Written
| Artifact | Field written | Value |
|---|---|---|
| ... | ... | ... |

## Proposed but Unconfirmed
| Artifact | Proposed value | Reason skipped |
|---|---|---|
| ... | ... | ... |

## Unresolved Gaps (manual follow-up required)
| Artifact | Missing field | Notes |
|---|---|---|
| ... | ... | ... |
```

All unresolved gaps require manual intervention before Critic Group F passes.
