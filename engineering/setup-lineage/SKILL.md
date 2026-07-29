---
name: setup-lineage
description: Retrofit an existing repo with lineage frontmatter and inline source-reference fields across the FS→SRS→ADR→Spec→Ticket chain. Standalone skill — not part of setup-skills.
disable-model-invocation: true
---

## Phase 1 — Auto-Inference (FS→SRS only)

1. Scan all FS documents at `.data/requirements/*-FS-*.md`. For each, extract requirement IDs and one-line summaries.
2. Scan all SRS documents at `.data/requirements/*-SRS-*.md`. For each, extract requirement IDs and one-line summaries.
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
- **SRS** defines the system contracts that satisfy FS: entities, interfaces, workflows, and invariants. Companion API/Data-View documents project an SRS and cite its requirement IDs.
- **ADR** records lower-level architectural or implementation decisions that realize an existing SRS contract; an ADR does not need a one-to-one SRS requirement when a broader interface or invariant governs it.

Before treating an ADR as unanchored, search the SRS and companions marked `lineage-rules: companion of SRS` for the governing capability, interface, entity, workflow, or invariant. A companion may locate a cited SRS requirement ID but cannot itself anchor the ADR. Anchor to that validated SRS ID when it covers the ADR's behavior, even if the ADR selects the concrete schema, library, validation method, storage shape, or provider translation.

Only when no existing SRS requirement ID covers the ADR's behavior, grill a proposed new SRS requirement. If that requirement has no defensible product outcome or constraint in FS, grill and define a new FS requirement first. Do not create a duplicate SRS requirement merely because the ADR is more detailed than its existing system contract.

Work through each artifact type that has unresolved chain links. Ask the user for each missing anchor:

| Artifact | Missing field | Question to ask |
|----------|---------------|-----------------|
| SRS item | `**Source FS**:` (no match from Phase 1) | "Which FS requirement does `<SRS-ID>` trace to? Options: existing ID / create new FS item / skip" |
| ADR | `**Source SRS**:` | "Which SRS requirement does ADR `<filename>` trace to? Provide an SRS ID." |
| Spec | `**Source ADR**:` | "Which ADR(s) does this spec derive from? Provide paths under `docs/adr/`." |
| Ticket | `**Spec**:` or `**Source ADR**:` | "Does this ticket trace to a spec slug (`.scratch/<slug>/spec.md`) or directly to an ADR?" |

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
| Ticket (adr-direct) | `ticket` (+ `ticket-subtype: adr-direct`) | structured rule list referencing ADR |
| Companion | appropriate type | `companion of SRS` + `source-srs:` path |

### 3.2 Inline source-reference fields

Write `**Source X**:` fields to each artifact body, one field per artifact, immediately after the frontmatter block:

- FS: no source field (root)
- SRS: `**Source FS**: <FS-ID>`
- ADR: `**Source SRS**: <SRS-ID>`
- Spec: `**Source ADR**: docs/adr/<filename>.md`
- Ticket (spec-linked): `**Spec**: <feature-slug>`
- Ticket (adr-direct): `**Source ADR**: docs/adr/<filename>.md`

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
