# ADR-0067: to-tickets Lineage Fields and Block Conditions

**Status**: Approved

**Context**

ADR-0054 lists to-tickets in the scope of the lineage chain (Spec→Ticket). The to-tickets skill produces ticket files at `.scratch/<feature-slug>/issues/*.md`. Without explicit lineage obligations, tickets authored by to-tickets may lack `lineage-rules` frontmatter and source fields, making them invisible to critic Group F and breaking the mandatory chain.

**Decision**

The to-tickets skill must populate the following lineage fields on every ticket it authors or updates:

1. **Frontmatter** (machine-readable for Group F):

   For spec-linked tickets (default):
   ```yaml
   ---
   artifact-type: ticket
   lineage-rules:
     - "Ticket must reference its source spec"
     - "Ticket may additionally reference source ADRs for cross-cutting concerns"
   ---
   ```

   For ADR-direct tickets (see ADR-0056 §3):
   ```yaml
   ---
   artifact-type: ticket
   ticket-subtype: adr-direct
   lineage-rules:
     - "Ticket must reference at least one source ADR"
     - "Spec field is intentionally omitted: this ticket traces directly to an ADR"
   ---
   ```

2. **Inline fields** (human-readable, critic-parseable):

   | Field | Type | Required for subtype | Example |
   |-------|------|----------------------|---------|
   | `**Spec**:` | single | spec-linked (mandatory) | `feature-slug` |
   | `**Source ADR**:` | list | adr-direct (mandatory); spec-linked (optional) | `docs/adr/0034-foo.md` |

3. **Population timing**: Fields are written before tickets are finalized. to-tickets must resolve the source spec from the conversation context (the spec that triggered the ticket generation session).

4. **Block conditions** (to-tickets must not finalize tickets if any of these are true):

   For spec-linked tickets:
   - No `**Spec**:` field is present
   - The spec slug does not resolve to an existing file at `.scratch/<slug>/spec.md`

   For ADR-direct tickets:
   - `ticket-subtype: adr-direct` is declared but no `**Source ADR**:` field is present
   - Any listed ADR path does not resolve to an existing file in `docs/adr/`

   For all tickets:
   - Block action: surface the gap to the user and request the missing field before writing ticket files

5. **Declaring ADR-direct tickets**: to-tickets may propose ADR-direct subtype when the user's request references an ADR directly with no spec context. The user must confirm the subtype before to-tickets applies it.

**Consequences**

- Tickets produced by to-tickets are always visible to critic Group F
- The Ticket→Spec and Ticket→ADR links in the mandatory chain are enforced at authoring time
- to-tickets cannot silently produce orphaned tickets
- The ADR-direct ticket subtype is a sanctioned exception path with explicit frontmatter, not an undocumented omission
- Manually authored tickets are subject to the same standards via Group F post-hoc audit (see ADR-0055)
