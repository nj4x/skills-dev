---
name: SRS-skill
description: Transform FS requirements into capability-level SRS contracts. Use when creating or revising SRS from FS/EARS requirements; routes invocation and realization mechanisms to ADRs.
disable-model-invocation: true
---

# FS-to-SRS Skill

> **⚠️ IMPORTANT**: This skill transforms Feature Set (FS) requirements into Software Requirements Specification (SRS) documents. It REQUIRES an existing FS/EARS document as input and has MANDATORY confirmation checkpoints.

This skill helps create capability-level SRS documents from high-level Feature Set requirements by:
- Filtering requirements relevant to the system contract
- Grouping requirements by actors and stakeholders
- Identifying entities, lifecycle behavior, and safety constraints
- Identifying event semantics
- Maintaining traceability to source FS requirements

Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary). Route invocation and realization mechanisms to an ADR; do not put them in SRS.

## Workflow Summary with Checkpoints

### Phase 1: Initialization (BLOCKING)
1. **CHECKPOINT #1** - Confirm skill activation and source document
   - Action: Ask user to confirm FS-to-SRS skill usage
   - Action: Identify source FS document(s)
   - Condition: WAIT for explicit user confirmation
   - If user activated via `use_skill` → Proceed to source identification

### Phase 2: Analysis & Extraction
2. **Step 1** - Read SRS structure documentation
3. **Step 2** - Load and analyze source FS document(s)
4. **Step 3** - Filter for system-contract requirements
5. **Step 4** - Group requirements by actors/stakeholders
6. **Step 5** - Extract entities, lifecycle behavior, and safety constraints
7. **Step 6** - Identify event semantics

### Phase 3: Generation
8. **Step 7** - Generate SRS requirements with FS attribution
   - **Step 7.4** - FS Anchor Preflight: validate/resolve `**Source FS**:` for every requirement; inline FS authoring if missing
9. **Step 8** - Quality check and validation

### Phase 4: Iterative Refinement Loop (BLOCKING)
10. **CHECKPOINT #2** - Begin refinement loop
    - **Step 9.1**: Present draft SRS to user + provide improvement suggestions
    - **Step 9.2**: IF user requests changes → Incorporate feedback
    - **Step 9.3**: Validation against source FS documents
    - **Step 9.4**: Ask user: "Are you satisfied with these SRS requirements?"
      - IF user says NO → GOTO Step 9.1
      - IF user says YES → PROCEED to Phase 5

### Phase 5: Finalization
11. **Step 10** - Write SRS document to file
    - Condition: ONLY execute after explicit user approval at Step 9.4

For API contracts, use-case sequences, or data realization, create an ADR through `/grill-with-docs`; do not generate companion documents.

### Decision Rules
| Condition | Action |
|-----------|--------|
| User has NOT confirmed at Checkpoint #1 | WAIT - Do not proceed |
| User has NOT approved at Checkpoint #2 | LOOP - Return to Step 9.1 |
| SRS requirement has no `**Source FS**:` after Step 7.4 preflight | BLOCK - Do not finalize; surface unanchored list |
| User says "yes", "approved", "satisfied", "proceed" | PROCEED to next phase |
| User provides feedback or says "no" | INCORPORATE changes, stay in loop |

---

## 0. Confirm Skill Activation (MANDATORY CHECKPOINT #1)

**⛔ STOP - Do not proceed without user confirmation**

Before proceeding with ANY SRS generation work:
1. Ask the user: "I can help transform FS requirements into an SRS document. Would you like me to use the FS-to-SRS skill for this task?"
2. Identify the source FS document(s):
   - Ask: "Please provide the path to the FS/EARS requirements document to transform"
   - OR identify from user's request if already provided
3. Confirm the target system/domain (e.g., "Role Management", "Group Management")
4. **Wait for explicit user confirmation**
5. Only after receiving confirmation, proceed to step 1

> **Note**: If user's task explicitly mentions "use FS-to-SRS" or activates this skill via `use_skill`, this checkpoint is satisfied but source document identification is still required.

---

## 1. Read SRS Structure Documentation

Read the following documentation files to understand SRS structure and transformation rules:

- [SRS-Structure.md](<skill dir>/docs/SRS-Structure.md) - SRS document template
- [Entity-Extraction.md](<skill dir>/docs/Entity-Extraction.md) - Entity identification rules
- [Event-Types.md](<skill dir>/docs/Event-Types.md) - Event modeling patterns
- [Backend-Filtering.md](<skill dir>/docs/Backend-Filtering.md) - Backend relevance criteria

---

## 2. Load and Analyze Source FS Document(s)

### 2.1 Source Document Access

Load the source FS/EARS document(s) provided by the user:

1. Use `read_file` to load the FS document
2. Parse the document structure:
   - Identify requirement categories (e.g., STRUC, NAME, CRUD, MEMB)
   - Extract individual requirements with their IDs
   - Note EARS patterns used (Ubiquitous, Event-driven, etc.)
3. Build an internal model of all requirements for transformation
4. **Load all existing FS documents** from `.data/requirements/*-FS-*.md` into a lookup table of known FS IDs.

### 2.2 Document Metadata Extraction

Extract from source FS document:
- Document ID (e.g., `GRP-FS-2.0`)
- Version information
- Source references (Confluence links, page IDs)
- Category structure

### 2.3 Source Reference Generation

When referencing source wiki documents, **use MCP tool `generate_wiki_link`** to generate Confluence URLs:
- Call `generate_wiki_link(path="./path/to/wiki_page_directory")` 
- The tool returns both `url` (plain link) and `markdown` (formatted `[Title](URL)`)
- Example: `generate_wiki_link(path=".data/FeatureSets_v2.0/Group_Policy_1590539350")`
- Use the `markdown` output directly in Source columns of requirement tables

---

## 3. Filter for System-Contract Requirements

Apply filtering criteria from [Backend-Filtering.md](<skill dir>/docs/Backend-Filtering.md):

### 3.1 Include Criteria (Requirements to KEEP)

Requirements belong in SRS when they define a capability, lifecycle behavior, or safety contract:

| Criterion | Examples |
|-----------|----------|
| **Data persistence** | Create, store, update, delete operations |
| **Business logic** | Validation rules, calculations, transformations |
| **Authorization** | Permission checks, role-based access |
| **External interaction semantics** | Required information exchange or event meaning, not transport or invocation |
| **Data retrieval** | Query, search, filter, list operations |
| **State management** | State transitions, workflow logic |
| **Constraint enforcement** | Uniqueness, referential integrity |

### 3.2 Exclude Criteria (Requirements to SKIP)

Requirements are front-end only if they ONLY involve:

| Criterion | Examples |
|-----------|----------|
| **Pure UI display** | "Display X at top of list", "Show button" |
| **UI interaction** | "When button clicked", "Highlight selected" |
| **UI layout** | "Position on screen", "Display order" |
| **Client-side validation** | Field highlighting, instant feedback |
| **Navigation** | "Navigate to page", "Open modal" |

### 3.3 Hybrid Requirements

Some requirements have both front-end and back-end aspects:
- Extract the back-end portion
- Note the UI trigger but focus on system behavior
- Example: "When Delete button clicked, system shall remove the member" → Focus on "system shall remove the member"

### 3.4 Create Filtered Requirements List

Create a mapping table:

| FS Requirement ID | Include/Exclude | Reason |
|-------------------|-----------------|--------|
| GRP-FS-STRUC-001 | Include | Data persistence - nested structure |
| GRP-FS-TCHR-016 | Exclude | Pure UI display ordering |
| GRP-FS-TCHR-015 | Include (partial) | Delete operation (ignore UI trigger) |

---

## 4. Group Requirements by Actors and Stakeholders

### 4.1 Actor Identification

Identify all actors from the FS document:
- Extract from permission matrices
- Extract from requirement descriptions ("allow users with X role")
- Categorize by role type:
  - **Internal actors**: System administrators, service owners
  - **External actors**: Client organizations, end users
  - **System actors**: Automated processes, other systems

### 4.2 Stakeholder Identification

Identify stakeholders affected by or interested in requirements:
- Service/component owners
- Dependent systems
- Business units

### 4.3 Group Structure

Create logical groupings following this hierarchy:

```
[System Domain] (e.g., SAB Role Management)
├── [Feature Set] (e.g., System Role Management)
│   ├── Actor: [Primary Actor] (CRUD permissions)
│   ├── Permissions: [Required permissions]
│   ├── Stakeholders: [Affected parties]
│   └── Requirements
│       ├── [Requirement Group 1] (e.g., Create System Role)
│       ├── [Requirement Group 2] (e.g., Update System Role)
│       └── ...
```

### 4.4 Metadata Per Group

Each requirement group should have:

```markdown
**Actor**: [Actor name] ([CRUD permissions])
**Permissions**: [Required permissions or N/A]
**Stakeholders**: 
- [Stakeholder 1]
- [Stakeholder 2]
**Feature Sets**: [Source FS references]
**Since**: [Document ID Version]

> **⚠️ "Since" Version Rule**: The `Since` field MUST use the version from the **Document ID** (e.g., `2.0` from `GRP-SRS-2.0`), NOT the frequently-updated `Version` field in the Document Information table (e.g., `2.29`). The Document ID version represents the feature release version.
```

---

## 5. Extract Entities and Attributes

Follow rules in [Entity-Extraction.md](<skill dir>/docs/Entity-Extraction.md):

### 5.1 Entity Identification

Identify entities from requirements by looking for:
- Nouns that are created, read, updated, or deleted
- Objects with identifiable attributes
- Objects with relationships to other entities

### 5.2 Attribute Extraction

For each entity, extract attributes from requirements:

| Attribute Pattern | Example | Extracted |
|-------------------|---------|-----------|
| "The system shall take X as input" | "take RoleName, RoleDescription, PrivilegeList as inputs" | RoleName, RoleDescription, PrivilegeList |
| "The system shall return X in response" | "return RoleId and Version:1 in response" | RoleId, Version |
| "The system shall create X flag/tag" | "create immutable flag IsSystemRole:true" | IsSystemRole |

### 5.3 Entity Documentation

Create entity reference table:

| Entity | Attributes | Required | Immutable | Source FS |
|--------|------------|----------|-----------|-----------|
| SystemRole | RoleId | Yes | Yes | GRP-FS-ROLE-001 |
| | RoleName | Yes | No | |
| | RoleDescription | No | No | |
| | PrivilegeList | Yes | No | |
| | IsSystemRole | Auto | Yes | |
| | Version | Auto | No | |

---

## 6. Identify Event Types

Follow rules in [Event-Types.md](<skill dir>/docs/Event-Types.md):

### 6.1 Event Triggers

Identify events from requirements with patterns:
- "When [action occurs]..."
- "Upon [event]..."
- "After [operation]..."

### 6.2 Event Classification

| Type | Description | Example |
|------|-------------|---------|
| **Consumed** | Events received from external systems | UserDeleted, OrganizationUpdated |
| **Produced** | Events published by this system | RoleCreated, MembershipChanged |
| **Internal** | Events within the system | ValidationCompleted |

### 6.3 Event Documentation

Create event reference table:

| Event Name | Type | Trigger | Attributes | Source FS |
|------------|------|---------|------------|-----------|
| RoleCreated | Produced | Role creation successful | RoleId, RoleName, Version | GRP-FS-CRUD-001 |
| MemberAdded | Produced | Member added to group | GroupId, MemberId, Role | GRP-FS-MEMB-010 |

---

## 7. Generate SRS Requirements with FS Attribution

### 7.1 SRS Requirement Format

Each SRS requirement should follow this structure:

```markdown
### [SRS-ID] [Requirement Title]

- [Bullet point requirement statement]
- [Additional requirement detail]
- [Observable preconditions, postconditions, invariants, or safety conditions]

**Source FS**: [FS Requirement ID(s)]
```

### 7.2 ID Encoding

SRS requirement IDs follow this pattern:

```
[DOMAIN]-[TYPE]-[VERSION].[SECTION].[SUBSECTION]

Examples:
- SAB-ROLE-FR-1.0.0  (SAB Role, Functional Requirement, v1.0, section 0)
- SAB-ROLE-FR-2.0.1  (SAB Role, Functional Requirement, v2.0, section 1)
```

Where:
- **DOMAIN**: System domain abbreviation (e.g., SAB-ROLE, SAB-GRP)
- **TYPE**: FR (Functional Requirement), NFR (Non-Functional), TR (Technical)
- **VERSION**: Major.Minor version
- **SECTION**: Requirement group number
- **SUBSECTION**: Requirement number within group

### 7.3 Attribution

Every SRS requirement MUST trace back to source FS requirements:

```markdown
**Source FS Requirements:**
- GRP-FS-CRUD-001: The system shall allow users with Super Admin role to create groups.
- GRP-FS-CRUD-004: When a group is created, the system shall record...
```

### 7.4 FS Anchor Preflight (ADR-0058)

For every generated SRS requirement, ensure a `**Source FS**:` field is present and valid:

1. **Field present** — validate the cited FS ID exists in the lookup table built at Step 2.1; if not found, flag error and block finalization.
2. **Field absent** — run the inline FS authoring flow:
   a. Ask: "Which FS requirement does SRS requirement `<ID>` trace to?"
   b. If the user names an existing FS ID: validate it in the lookup table; if not found, flag error.
   c. If no matching FS item exists, offer: "Create a new FS requirement now?"
      - **Yes**: Draft the requirement in EARS format, present for user approval, write to the appropriate FS document (and update the lookup table), then populate `**Source FS**:` in the SRS requirement.
      - **No**: Mark the SRS requirement as **unanchored** — Step 9.3 blocks finalization until all unanchored requirements are resolved.

---

## 9. Iterative Refinement Loop (MANDATORY CHECKPOINT #2)

> **⛔ CRITICAL**: This section is MANDATORY. You MUST NOT skip to Section 10 without completing at least one full iteration and receiving explicit user confirmation.

### 9.1 Present Draft and Ask for Feedback (REQUIRED)

**⛔ STOP - Present SRS and wait for user response**

After generating the SRS in steps 3-8, you MUST:

1. **Present the draft SRS** to the user (in a readable format, not written to file yet)
2. **Self-analyze** the generated SRS for:
   - Missing lifecycle, safety, or edge conditions
   - Invocation or realization mechanisms that belong in an ADR
   - Entity attribute gaps
   - Authorization scenarios not covered
   - Event handling gaps
3. **Provide improvement suggestions** to the user
4. **Ask explicitly**: "Would you like to make any changes, additions, or refinements to this SRS?"
5. **Wait for user response** - Do NOT proceed until user responds

### 9.2 Generate New Version (if changes requested)

Based on user feedback:
- Indicate what changed from the previous version
- Use **Added**, **Modified**, **Removed** markers

### 9.3 Validation Against Source FS

Cross-reference every SRS requirement against source FS:
- Verify FS reference is accurate
- Ensure SRS correctly interprets FS intent
- Flag any SRS requirements without FS backing
- **Block SRS finalization** if any new or materially edited requirement defines an invocation or realization mechanism; rewrite it to a capability, lifecycle, or safety contract and route the mechanism to an ADR.
- **Block SRS finalization** if any requirement still carries no `**Source FS**:` field after the Step 7.4 preflight; surface the list of unanchored requirements and return to Step 9.1

### 9.4 Confirmation Checkpoint (REQUIRED)

**⛔ STOP - Explicit confirmation required before proceeding**

Ask the user: **"Are you satisfied with this SRS, or would you like further refinements?"**

- **If user says NO**: Return to step 9.1
- **If user says YES**: Proceed to step 10

### 9.5 Single Refinement Mode (ALTERNATIVE)

When the user requests **iterative refinement** with individual checkpoints (e.g., "refine one by one", "checkpoint after each refinement"), use this alternative workflow:

**Trigger phrases**: "refine", "one by one", "checkpoint after each", "iterative refinement", "process refinements individually"

**Single Refinement Loop:**

1. **Wait for user's refinement instruction** (one specific change request)

2. **Apply the single refinement:**
   - Make ONLY the requested change
   - Do NOT make additional improvements unless asked
   - Update the SRS to reflect the change

3. **Present checkpoint:**
   - Show the specific change made (before/after if applicable)
   - Show the affected requirement(s) or section(s) in full
   - Briefly describe what was changed

4. **Ask continuation question:**
   
   **"Refinement applied. Would you like to:**
   - **Provide another refinement instruction?**
   - **Finalize and write to file?"**

5. **Decision handling:**
   - **If user provides another refinement** → Return to step 1
   - **If user says "finalize", "done", "write", "save"** → Proceed to Section 10

---

## 10. Write SRS Document to File

### 10.1 Output Location

Write to: `<Project Root>/.data/requirements/[Domain]-SRS-[Version].md`

Example: `.data/requirements/Role-Management-SRS-2.0.md`

### 10.2 Document Structure

Follow template in [SRS-Structure.md](<skill dir>/docs/SRS-Structure.md).

Every SRS document must begin with this YAML frontmatter block:

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

```markdown
# [Domain] | Software Requirements Specification

## Document Information
- **Document ID**: [ID]
- **Version**: [Version]
- **Source FS**: [FS Document Reference]
- **Category**: SRS
- **Status**: [Draft/Final]

## Source Feature Sets

| Feature Set | Document ID | Source |
|-------------|-------------|--------|
| [Name] | [ID] | [URL] |

---

## Entity Reference

| Entity | Attributes | Type | Required | Immutable |
|--------|------------|------|----------|-----------|
| ... | ... | ... | ... | ... |

---

## Event Reference

| Event Name | Type | Trigger | Attributes |
|------------|------|---------|------------|
| ... | ... | ... | ... |

---

## [Section 1.0] [Feature Set Name]

### Characteristics
[Description of the feature set]

### Metadata
**Actor**: [Actor(s)]
**Permissions**: [Required permissions]
**Stakeholders**: [Stakeholder list]
**Since**: [Version]

### [Section 1.0.0] [Requirement Name]

[Capability, lifecycle, and safety contract]

---

## Appendix A: FS-to-SRS Traceability

| SRS ID | FS ID(s) | Description |
|--------|----------|-------------|
| ... | ... | ... |
```

---
