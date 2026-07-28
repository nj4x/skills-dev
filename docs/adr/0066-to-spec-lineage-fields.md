# ADR-0066: to-spec Lineage Fields and Block Conditions

**Status**: Approved

**Context**

ADR-0054 lists to-spec in the scope of the lineage chain (ADR→Spec→Ticket). The to-spec skill produces spec documents at `.scratch/<feature-slug>/spec.md`. Without explicit lineage obligations, specs authored by to-spec may lack `lineage-rules` frontmatter and `**Source ADR**:` fields, making them invisible to critic Group F and breaking the mandatory chain.

**Decision**

The to-spec skill must populate the following lineage fields on every spec it authors or updates:

1. **Frontmatter** (machine-readable for Group F):
   ```yaml
   ---
   artifact-type: spec
   lineage-rules:
     - "Every spec section must reference at least one source ADR"
     - "Source ADR must exist in docs/adr/ and be in Approved status"
   ---
   ```

2. **Inline fields** (human-readable, critic-parseable):

   | Field | Type | Example | Notes |
   |-------|------|---------|-------|
   | `**Source ADR**:` | list | `docs/adr/0034-foo.md, docs/adr/0035-bar.md` | One or more ADR paths |

3. **Population timing**: Fields are written before the spec is finalized (before to-spec returns the artifact to the user for review). to-spec must resolve source ADRs from the conversation context or from a direct user declaration.

4. **Block conditions** (to-spec must not finalize the spec if any of these are true):
   - No `**Source ADR**:` field is present in the spec body
   - Any listed ADR path does not resolve to an existing file in `docs/adr/`
   - Any listed ADR file does not have `**Status**: Approved` (checked via body-text — informal convention; will be formalized separately)
   - Block action: surface the gap to the user and request an ADR path or initiate grill-with-docs to produce the missing ADR before proceeding

5. **When source ADRs are unknown**: If the user has not specified which ADRs the spec derives from, to-spec must ask before finalizing. It may not leave `**Source ADR**:` blank or set it to a placeholder.

**Consequences**

- Specs produced by to-spec are always visible to critic Group F
- The Spec→ADR link in the mandatory chain is enforced at authoring time
- to-spec cannot silently produce an orphaned spec
- Users are prompted to identify or create ADRs before spec work proceeds
- Manually authored specs are subject to the same standards via Group F post-hoc audit (see ADR-0055)
