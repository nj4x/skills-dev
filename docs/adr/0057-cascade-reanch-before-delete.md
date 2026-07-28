# ADR-0057: Cascade Re-Anchor-Before-Delete

**Status**: Approved

**Context**

When an upstream artifact (FS, SRS, ADR, or spec) is deleted, all downstream artifacts that trace to it become orphaned. Orphaned artifacts are a form of technical debt—they reference deleted sources and break lineage.

**Decision**

Before any artifact is deleted, **all downstream dependents must be re-anchored to other valid sources or explicitly deleted themselves.**

Flow for each artifact type:

1. **FS deletion** (user initiates):
   - Scan all SRS documents for `**Source FS**: <ID>`
   - If found, surface orphans and block deletion
   - User must re-anchor each SRS item (to another FS item or new FS item)
   - Only after all re-anchored, allow FS item deletion

2. **SRS deletion** (via contradiction resolution or user request):
   - Scan all ADRs for `**Source SRS**: <ID>`
   - Block and surface orphans; require re-anchoring
   - Same cascade rule applies

3. **ADR deletion**:
   - Scan all specs for `**Source ADR**: <ID>`
   - Block and surface orphans; require re-anchoring

4. **Spec deletion**:
   - Scan all tickets for `**Spec**: <spec-slug>`
   - If tickets cite this spec by slug, block deletion; re-anchor or delete tickets
   - Note: `**Source ADR**:` in a ticket traces to an ADR, not to the spec; it does not create a dependency on the spec being deleted and must not be scanned here

**Scan-Integrity Policy**

Convention-based scanning (steps 1–4) relies on artifact location conventions from ADR-0056. The following policies govern scan completeness:

- **Non-standard paths**: If an artifact is found outside the expected convention paths (e.g., a ticket not under `.scratch/<feature-slug>/issues/`), it is treated as a scan gap and flagged as a warning in the deletion output. Deletion proceeds only after user acknowledges the warning.
- **Lookup failures**: If a convention path glob returns no results (e.g., `.scratch/*/issues/*.md` matches nothing), this is surfaced as a scan warning, not an error. The user must confirm no dependents exist before deletion proceeds.
- **Unknown artifact types**: Artifacts whose type cannot be determined from path convention are excluded from dependency scanning; this is flagged in the output.
- **Scan completeness gate**: Before blocking or permitting deletion, the skill reports the scan scope (paths searched, files found, files matched) so the user can verify coverage.

**Consequences**

- No orphaned references ever exist in the system
- Lineage chain is always complete and validatable
- Deletion is a heavy operation (cascades check) but ensures integrity
- Users cannot accidentally leave broken references behind
- Re-anchoring forces deliberate decisions about deprecation vs. withdrawal
