# ADR-0063: Companion Documents Inherit SRS Lineage

**Status**: Approved

**Context**

SRS-skill generates companion documents (API Definition, Use Case Diagrams, Data Views) as derived views of the SRS. These documents are not independent artifacts in the lineage chain; they are projections of the SRS.

Companion documents should be validated to ensure they don't introduce structure or obligations not present in the source SRS.

**Decision**

Companion documents carry SRS-lineage frontmatter and validation:

1. **Frontmatter**:
   ```yaml
   ---
   artifact-type: api-definition
   lineage-rules: companion of SRS
   source-srs: .data/requirements/Group-SRS-2.0.md
   ---
   ```

2. **Inline field**:
   ```markdown
   **Source SRS**: SAB-GRP-FR-2.0
   ```
   (Each section of the companion doc cites its source SRS requirement)

3. **Validation** (existing SRS-skill Step 11.4, now formalized):
   - Every entity, event, API, use case, or field in the companion must have an explicit SRS line anchor proving it's already stated in the source SRS
   - No new structure invented by the companion (new entities, events, APIs, enums) unless the SRS explicitly requires it
   - Prose-only obligations in the SRS are rendered as schema notes, validation rules, or use-case annotations in companions, not as new schema elements

4. **Critic validation**:
   - Critic Group F validates that each companion's `source-srs` document exists
   - (Detailed structural provenance auditing remains in SRS-skill Step 11.4; Group F does not re-audit structure)

**Consequences**

- Companions are clearly marked as SRS projections, not independent artifacts
- Lineage chain does not branch (companions are siblings to SRS, not children)
- Existing SRS-skill provenance checks (Step 11.4) remain authoritative
- Skills that use companion outputs (api-skill, data-view-skill) inherit SRS traceability
