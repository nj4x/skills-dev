# ADR-0060: Critic Group F—Lineage Auditing and Convention-Based Lookup

**Status**: Approved

**Context**

Critic currently has Groups A–D (common review lenses) plus an artifact-specific fifth group per artifact type. Lineage validation is a cross-cutting concern that applies to all artifacts, not a single artifact type.

**Decision**

Add **Group F (Lineage)** as a dedicated critic lens that runs on all artifact types:

1. **Activation — two stages**:

   **Stage 1 — Universal pre-gate (always runs)**:
   Group F begins by identifying all in-scope artifacts using the path-convention globs defined in ADR-0056 §4. For every matched artifact it checks for the presence of a `lineage-rules` frontmatter key:
   - Artifact has no `lineage-rules` key → **Major** finding: "Artifact missing `lineage-rules` frontmatter; lineage cannot be audited." (No further Group F checks are run on this artifact.)
   - Exception: artifacts under `docs/adr/` whose filename prefix is `< 0056` (i.e., `0001-` through `0055-`) are flagged as **Informational** (legacy artifact). The user must confirm whether to retrofit.
   - to-spec and to-tickets output artifacts (specs at `.scratch/<slug>/spec.md`, tickets at `.scratch/<slug>/issues/*.md`) are **in scope** and must carry `lineage-rules` frontmatter. Absence is flagged as **Major**.
   - Artifact has `lineage-rules: exempt` → **Informational** note that the artifact has opted out; no further Group F checks.

   **Stage 2 — Content-validation gate (runs only when `lineage-rules` is non-empty, non-`root`, non-`exempt`)**:

2. **Validation logic**:
   - Read the artifact's `lineage-rules` frontmatter
   - For each `**Source X**:` field in the artifact body:
     - Extract the referenced IDs
     - Use convention-based lookup to locate the source document (FS, SRS, ADR locations)
     - Verify each ID exists in its source document
     - Flag missing IDs as Critical, dangling references as Critical

3. **Convention-based lookup**:
   - FS IDs (pattern `*-FS-*`): search `.data/requirements/*-FS-*.md`
   - SRS IDs (pattern `*-FR-*`, `*-NFR-*`, etc.): search `.data/requirements/*-SRS-*.md`
   - ADR IDs: search `docs/adr/*.md` by filename
   - Spec slugs: search `.scratch/*/spec.md`
   - Ticket files: search `.scratch/*/issues/*.md`

4. **Findings**:
   - Missing anchor (e.g., SRS with no `**Source FS**:`): Major
   - Dangling reference (ID not found in source): Critical
   - Circular reference (A traces to B traces to A): Critical
   - Source document not found: Critical

5. **Special cases**:
   - FS artifacts with `lineage-rules: root`: handled by Stage-2 gate exclusion — no further checks
   - Companion artifacts with `lineage-rules: companion of SRS`: restrict Stage-2 validation to `**Source SRS**:` field only; skip all other Source fields
   - ADR-direct tickets (`ticket-subtype: adr-direct` with a present `**Source ADR**:` field): `**Spec**:` is optional; skip the missing-anchor Major finding for the Spec anchor only. See ADR-0067.
   - Stage-2 gate treats blank, null, or empty-list `lineage-rules` identically to missing key — Stage-1 Major applies

**Consequences**

- Lineage violations are consistently detected across all artifact types
- No explicit path bookkeeping needed (convention-based)
- Critic can audit lineage independently of the authoring workflows
- Skills that pre-validate (SRS-skill, grill-with-docs) will rarely trigger Group F findings, but critic provides a safety net
