---
name: SRS-skill
description: Transform FS requirements into capability-level SRS contracts. Use when creating or revising SRS from FS/EARS requirements; routes invocation and realization mechanisms to ADRs.
disable-model-invocation: true
---

# SRS Skill

Transform Feature Set (FS) requirements into Software Requirements Specification (SRS) documents. Requires an existing FS/EARS document as input and two user confirmation gates.

Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary). Route invocation and realization mechanisms to an ADR; do not put them in SRS.

For API contracts, use-case sequences, or data realization, create an ADR through `/grill-with-docs`; do not generate companion documents.

## 0. Confirm Activation

Ask the user to confirm SRS skill usage, identify the source FS document(s), and confirm the target system/domain. Proceed only after receiving confirmation.

If the user's task explicitly mentions "use SRS-skill", this gate is satisfied; source document identification is still required.

## 1. Read SRS Structure Documentation

Read:

- [SRS-Structure.md](docs/SRS-Structure.md)
- [Entity-Extraction.md](docs/Entity-Extraction.md)
- [Event-Types.md](docs/Event-Types.md)
- [Backend-Filtering.md](docs/Backend-Filtering.md)

## 2. Load and Analyze Source FS Document(s)

1. Use `read_file` to load the FS document
2. Parse structure: identify requirement categories, extract individual requirement IDs, note EARS patterns used
3. Build an internal model of all requirements
4. Load all existing FS documents from `.data/requirements/*-FS-*.md` into a lookup table of known FS IDs

Extract document metadata: Document ID, version, source references.

When referencing wiki documents, use MCP tool `generate_wiki_link(path="./path/to/wiki_page_directory")` — use the `markdown` output in Source columns.

## 3. Filter for System-Contract Requirements

Apply filtering criteria from [Backend-Filtering.md](docs/Backend-Filtering.md). Create a mapping table:

| FS Requirement ID | Include/Exclude | Reason |
|-------------------|-----------------|--------|
| GRP-FS-STRUC-001 | Include | Data persistence - nested structure |
| GRP-FS-TCHR-016 | Exclude | Pure UI display ordering |
| GRP-FS-TCHR-015 | Include (partial) | Delete operation (ignore UI trigger) |

## 4. Group Requirements by Actors and Stakeholders

Identify actors from permission matrices and requirement descriptions; categorize as internal, external, or system actors. Identify stakeholders affected by requirements.

Structure groupings:

```
[System Domain]
├── [Feature Set]
│   ├── Actor: [Primary Actor] (CRUD permissions)
│   ├── Permissions: [Required permissions]
│   ├── Stakeholders: [Affected parties]
│   └── Requirements
│       ├── [Requirement Group 1]
│       └── ...
```

Each requirement group metadata:

```markdown
**Actor**: [Actor name] ([CRUD permissions])
**Permissions**: [Required permissions or N/A]
**Stakeholders**: 
- [Stakeholder 1]
**Feature Sets**: [Source FS references]
**Since**: [Document ID Version]
```

The `Since` field uses the version from the Document ID (e.g., `2.0` from `GRP-SRS-2.0`), not the frequently-updated `Version` field in the Document Information table.

## 5. Extract Entities and Attributes

Follow rules in [Entity-Extraction.md](docs/Entity-Extraction.md). Identify entities (nouns that are created, read, updated, or deleted) and extract their attributes.

## 6. Identify Event Types

Follow rules in [Event-Types.md](docs/Event-Types.md). Identify event triggers; classify as Consumed, Produced, or Internal.

## 7. Generate SRS Requirements with FS Attribution

### 7.1 Format

```markdown
### [SRS-ID] [Requirement Title]

- [Bullet point requirement statement]
- [Observable preconditions, postconditions, invariants, or safety conditions]

**Source FS**: [FS Requirement ID(s)]
```

### 7.2 ID Encoding

```
[DOMAIN]-[TYPE]-[VERSION].[SECTION].[SUBSECTION]

Examples:
- SAB-ROLE-FR-1.0.0
- SAB-ROLE-FR-2.0.1
```

Where DOMAIN is system domain abbreviation (e.g., SAB-ROLE, SAB-GRP), TYPE is FR/NFR/TR, VERSION is Major.Minor, SECTION is requirement group number, SUBSECTION is requirement number within group.

### 7.3 Attribution

Every SRS requirement must trace back to source FS requirements:

```markdown
**Source FS Requirements:**
- GRP-FS-CRUD-001: The system shall allow users with Super Admin role to create groups.
```

### 7.4 FS Anchor Preflight (ADR-0058)

For every generated SRS requirement, ensure a `**Source FS**:` field is present and valid:

1. **Field present** — validate the cited FS ID in the lookup table built at step 2; if not found, flag error and block finalization.
2. **Field absent** — run the inline FS authoring flow:
   a. Ask: "Which FS requirement does SRS requirement `<ID>` trace to?"
   b. If user names an existing FS ID: validate it; if not found, flag error.
   c. If no matching FS item exists, offer: "Create a new FS requirement now?"
      - **Yes**: Draft in EARS format, present for user approval, write to the FS document, update lookup table, populate `**Source FS**:`.
      - **No**: Mark as **unanchored** — step 9.3 blocks finalization until all unanchored requirements are resolved.

## 8. Quality Check and Validation

1. Cross-reference every SRS requirement against source FS documents
2. Verify all SRS requirements express capability, lifecycle, or safety contracts — not invocation or realization mechanisms
3. Flag any requirements that define an invocation or realization mechanism; rewrite to capability/lifecycle/safety contract and route mechanism to an ADR
4. Verify all entity attributes are accounted for
5. Verify event semantics are complete and correctly classified

## 9. Iterative Refinement Loop

### 9.1 Present Draft and Ask for Feedback

After generating SRS in steps 3–8:

1. Present the draft SRS to the user (not written to file yet)
2. Self-analyze for: missing lifecycle/safety/edge conditions; invocation or realization mechanisms belonging in an ADR; entity attribute gaps; authorization scenarios not covered; event handling gaps
3. Provide improvement suggestions
4. Ask: "Would you like to make any changes, additions, or refinements to this SRS?"
5. Wait for user response before proceeding

### 9.2 Generate New Version (if changes requested)

Mark changes with **Added**, **Modified**, **Removed** markers.

### 9.3 Validation Against Source FS

Cross-reference every SRS requirement against source FS. Block finalization if any requirement defines an invocation or realization mechanism, or carries no `**Source FS**:` field after the step 7.4 preflight. Surface all issues before blocking; return to step 9.1.

### 9.4 Confirmation Gate

Ask: "Are you satisfied with this SRS, or would you like further refinements?"

- User requests changes → return to step 9.1
- User confirms satisfaction → proceed to step 10

### 9.5 Single Refinement Mode

When the user requests iterative refinement with individual checkpoints ("refine one by one", "checkpoint after each refinement", "process refinements individually"):

1. Wait for a single refinement instruction
2. Apply only the requested change; do not make additional improvements
3. Show the specific change made (before/after if applicable) and the affected requirement(s)
4. Ask: "Refinement applied. Provide another refinement instruction, or say 'finalize' to write to file."
5. Another instruction → return to step 1; "finalize"/"done"/"write"/"save" → proceed to step 10

## 10. Write SRS Document to File

Write to: `<Project Root>/.data/requirements/[Domain]-SRS-[Version].md`

Follow template in [SRS-Structure.md](docs/SRS-Structure.md). Every SRS document must begin with this YAML frontmatter:

```yaml
---
artifact-type: srs
lineage-rules:
  - "Every SRS item must reference at least one FS item via **Source FS**:"
  - "If no matching FS item exists, user must confirm adding a new FS requirement"
  - "SRS must express capability, lifecycle, or safety contracts rather than invocation or realization mechanisms"
source-fs: .data/requirements/[Domain]-FS-[Version].md
---
```

## 11. Companion Document Lineage

When reviewing or updating existing companion documents (API Definitions, Use Case Diagrams, Data Views), apply lineage rules in [docs/Companion-Lineage.md](docs/Companion-Lineage.md).

New companion documents are not generated by this skill. New API contracts, use-case sequences, and data realization belong in an ADR authored through `/grill-with-docs`.
