# Lineage System ADR Manifest

Architecture decisions for implementing traceability and lineage rules across the requirements, engineering, and dev skills (FS-skill, SRS-skill, grill-with-docs, to-spec, to-tickets, wayfinder, code-review, implement).

Design Decisions Reached During Grilling — 14 ADRs captured:

- docs/adr/0054-lineage-chain-architecture.md
- docs/adr/0055-lineage-enforcement-split-skill-and-critic.md
- docs/adr/0056-lineage-frontmatter-and-field-standards.md
- docs/adr/0057-cascade-reanch-before-delete.md
- docs/adr/0058-srs-skill-inline-fs-authoring.md
- docs/adr/0059-grill-with-docs-preflight-srs-anchor.md
- docs/adr/0060-critic-group-f-lineage-auditing.md
- docs/adr/0061-code-review-lineage-enforcement.md
- docs/adr/0062-implement-skill-verify-then-check-checklists.md
- docs/adr/0063-companion-documents-inherit-srs-lineage.md
- docs/adr/0064-fs-skill-deletion-guards-and-stable-ids.md
- docs/adr/0065-setup-lineage-skill-for-retrofit.md
- docs/adr/0066-to-spec-lineage-fields.md
- docs/adr/0067-to-tickets-lineage-fields.md

---

## Session Ledger

| Role | Outcome |
|------|---------|
| orchestrator | b879f602-afcb-4e77-a0e6-0fabd76c91be |
| planner | complete |
| critic #1 | revise (major) — 7 majors |
| critic #2 | revise (major) — 1 major (ID-005 residual) |
| critic #3 | revise (major) — 1 new major (ADR-0060 §5 ADR-direct carve-out) |

## Critic Review

- **Final verdict:** revise
- **Severity:** major
- **Iterations used:** 3 of 3
- **Approval status:** ⚠ Reached MAX_ITERATIONS (3) without critic approval. Post-cap fix applied by orchestrator to ADR-0060 §5 (ADR-direct ticket carve-out). Remaining minor issues noted below.
- **Post-cap fix applied**: ADR-0060 §5 — added ADR-direct ticket carve-out (skip Spec: Major when ticket-subtype: adr-direct + Source ADR: present); clarified root handling; added companion Stage-2 restriction; defined blank/null/empty lineage-rules as Stage-1 Major.
- **Remaining minor issues (advisory)**:
  - ADR-0060 §3: Stage-1 discovery globs from ADR-0056 §4 may not cover `.scratch/` paths — verify glob coverage
  - ADR-0060 §5 legacy exception: 'pre-date ADR-0056 adoption' is ambiguous — pin to 'ADR number < 0056' or an adoption date
  - ADR-0066 §4: ADR status check (`**Status**: Approved`) relies on informal body-text convention — formalize in ADR-0056 in a future pass
