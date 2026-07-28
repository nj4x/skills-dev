# ADR-0054: Lineage Chain Architecture

**Status**: Approved

**Context**

Skills in the requirements, engineering, and dev groups (FS-skill, SRS-skill, grill-with-docs, to-spec, to-tickets, wayfinder, code-review) produce interconnected artifacts that must maintain traceability for understanding how product requirements flow through design decisions into implementation tickets.

Without explicit lineage rules, artifacts become orphaned when upstream sources change, and the chain of reasoning from requirement to code is invisible.

**Decision**

Establish a **lineage chain** that connects artifacts vertically:

```
FS (Product Requirements)
  ↓ traces-to
SRS (Software Requirements)
  ↓ traces-to
ADR (Architecture Decisions)
  ↓ traces-to
Spec (Implementation Specification)
  ↓ traces-to
Ticket (Implementation Task)
```

**Companion documents** (API Definition, Use Case Diagrams, Data Views) trace horizontally to their parent SRS, not vertically down the chain.

**Wayfinder** sits outside this chain—it is planning scaffolding, not a requirement artifact.

**Consequences**

- Every SRS item must cite at least one source FS item
- Every ADR must cite at least one source SRS item
- Every spec section must cite at least one source ADR
- Every ticket must cite its source spec or ADR (or both)
- Companion documents cite their parent SRS
- Cascade re-anchoring is required before any artifact deletion (FS→SRS→ADR→Spec→Ticket)
- Lineage validation becomes a first-class concern in skill workflows and critic auditing
