# ADR-0063: Companion Documents Inherit SRS Lineage

**Status**: Approved

**Context**

Existing companion documents (API Definition, Use Case Diagrams, Data Views) are derived views of the SRS. They are not independent artifacts in the lineage chain; they are legacy projections of the SRS.

New API contracts, use-case sequences, and data realization belong in the ADR that selects or changes the mechanism. New companions are not generated or extended. Existing companions remain readable and must not introduce obligations absent from their source SRS.

**Decision**

Existing companion documents retain SRS-lineage frontmatter and validation:

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

3. **Validation**:
   - Every entity, event, API, use case, or field in the companion must have an explicit SRS line anchor proving it's already stated in the source SRS
   - No new structure invented by the companion (new entities, events, APIs, enums) unless the SRS explicitly requires it
   - Prose-only obligations in the SRS are rendered as schema notes, validation rules, or use-case annotations in companions, not as new schema elements

4. **Critic validation**:
   - Critic Group F validates that each companion's `source-srs` document exists
   - (Detailed structural provenance auditing applies only when a legacy companion is deliberately reviewed; Group F does not re-audit structure)

**Consequences**

- Existing companions remain clearly marked as SRS projections, not independent artifacts
- Lineage chain does not branch (companions are siblings to SRS, not children)
- Existing companion provenance checks remain authoritative for legacy artifacts
- New API contracts, sequences, and data realization are co-located with their ADR rationale
- New work does not create or extend companions
