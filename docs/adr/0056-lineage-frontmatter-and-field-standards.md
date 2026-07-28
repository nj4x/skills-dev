# ADR-0056: Lineage Frontmatter and Field Standards

**Status**: Approved

**Context**

For critic to parse and validate lineage rules consistently across artifact types, frontmatter and inline field names must be standardized.

**Decision**

Every artifact includes:

1. **Frontmatter `lineage-rules`** (machine-readable for critic):
   ```yaml
   ---
   artifact-type: srs
   lineage-rules:
     - "Every SRS item must reference at least one FS item"
     - "If no matching FS item exists, user must confirm adding new FS requirement"
     - "SRS must flag contradictions with existing FS items for grilling"
   ---
   ```

   Special cases:
   - **FS documents**: `lineage-rules: root` (no upstream validation)
   - **Companion documents**: `lineage-rules: companion of SRS` (validates against parent SRS)

2. **Inline structured fields** (human-readable, critic-parseable):

   | Artifact | Field | Type | Example |
   |----------|-------|------|---------|
   | SRS requirement | `**Source FS**:` | list | `GRP-FS-CRUD-001, GRP-FS-MEMB-003` |
   | SRS companion | `**Source SRS**:` | list | `SAB-GRP-FR-2.0.1` |
   | ADR | `**Source SRS**:` | list | `SAB-GRP-FR-2.0.1, SAB-GRP-FR-2.0.2` |
   | Spec | `**Source ADR**:` | list | `docs/adr/0034-foo.md, docs/adr/0035-bar.md` |
   | Ticket | `**Source ADR**:` | list | `docs/adr/0034-foo.md` |
   | Ticket | `**Spec**:` | single | `spec-slug` or omitted (see ADR-direct ticket subtype below) |

3. **ADR-direct ticket subtype**

   A ticket may omit `**Spec**:` only when it is classified as an **ADR-direct ticket**. This subtype applies when:

   - The work item traces directly to an ADR without an intervening spec (e.g., infrastructure tasks, configuration changes, or cross-cutting concerns where no feature spec is warranted)
   - The ticket's frontmatter declares `ticket-subtype: adr-direct`
   - At least one `**Source ADR**:` field is present and resolves to a valid ADR

   Group F rules for ADR-direct tickets:
   - Missing `**Spec**:` is **not** a violation if `ticket-subtype: adr-direct` is set and `**Source ADR**:` is present and valid
   - Missing `**Spec**:` without `ticket-subtype: adr-direct` is a **Major** finding (ambiguous ticket)
   - Missing both `**Spec**:` and `**Source ADR**:` is a **Critical** finding regardless of subtype

   All other tickets (no `ticket-subtype` set) are assumed to be **spec-linked** and must carry a valid `**Spec**:` value.

4. **Convention-based lookup** (no explicit paths in lineage data):
   - FS documents: `.data/requirements/*-FS-*.md`
   - SRS documents: `.data/requirements/*-SRS-*.md`
   - ADRs: `docs/adr/*.md`
   - Specs: `.scratch/<feature-slug>/spec.md`
   - Tickets: `.scratch/<feature-slug>/issues/*.md`

**Consequences**

- Critic Group F can parse all artifacts uniformly via standard field names
- No path bookkeeping needed; IDs are looked up by convention
- Frontmatter documents rules explicitly, making them discoverable
- Skills can validate field presence and reference validity before finalizing
