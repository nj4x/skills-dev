---
name: SRS-skill
description: Transforms Feature Set (FS) requirements into Software Requirements Specification (SRS) documents for back-end systems. Use this skill when user asks to create SRS, technical requirements, or back-end specifications from existing FS/EARS requirements. This skill handles entity extraction, API derivation, event modeling, and test case generation.
disable-model-invocation: true
---

# FS-to-SRS Skill

> **⚠️ IMPORTANT**: This skill transforms Feature Set (FS) requirements into Software Requirements Specification (SRS) documents. It REQUIRES an existing FS/EARS document as input and has MANDATORY confirmation checkpoints.

This skill helps create back-end focused SRS documents from high-level Feature Set requirements by:
- Filtering requirements relevant to back-end systems
- Grouping requirements by actors and stakeholders
- Extracting entities with their attributes
- Identifying event types (consumed/produced)
- Deriving API interfaces and specifications
- Generating test cases with proper ID encoding
- Maintaining traceability to source FS requirements

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
4. **Step 3** - Filter for back-end relevant requirements
5. **Step 4** - Group requirements by actors/stakeholders
6. **Step 5** - Extract entities and their attributes
7. **Step 5.5** - Identify system dependencies
8. **CHECKPOINT #1.5** - Present dependencies for user approval (BLOCKING)
9. **Step 6** - Identify event types
10. **Step 7** - Derive API interfaces
11. **CHECKPOINT #2.5** - Confirm optional artifacts: Test Cases & Module View (BLOCKING)

### Phase 3: Generation
9. **Step 8** - Generate SRS requirements with FS attribution
10. **Step 9** - *(CONDITIONAL)* Generate test cases with encoded IDs — only if confirmed at Checkpoint #2.5
11. **Step 9.5** - *(CONDITIONAL)* Generate Module View Diagram — only if confirmed at Checkpoint #2.5
12. **Step 10** - Identify main use cases
13. **Step 11** - Quality check and validation

### Phase 4: Iterative Refinement Loop (BLOCKING)
12. **CHECKPOINT #2** - Begin refinement loop
    - **Step 12.1**: Present draft SRS to user + provide improvement suggestions
    - **Step 12.2**: IF user requests changes → Incorporate feedback
    - **Step 12.3**: Validation against source FS documents
    - **Step 12.4**: Ask user: "Are you satisfied with these SRS requirements?"
      - IF user says NO → GOTO Step 12.1
      - IF user says YES → PROCEED to Phase 5

### Phase 5: Finalization
14. **Step 13** - Write SRS document to file
    - Condition: ONLY execute after explicit user approval at Step 12.4
15. **Step 14** - Generate companion documents
    - API Definition Document ([DOMAIN]-API-Definition-[VERSION].md)
    - Use Case Diagrams Document ([DOMAIN]-Use-Case-Diagrams-[VERSION].md)

### Decision Rules
| Condition | Action |
|-----------|--------|
| User has NOT confirmed at Checkpoint #1 | WAIT - Do not proceed |
| User has NOT responded at Checkpoint #2.5 | WAIT - Do not generate test cases or module view |
| User declined test cases at Checkpoint #2.5 | SKIP Step 9, omit Test Cases and Appendix B from SRS |
| User declined module view at Checkpoint #2.5 | SKIP Step 9.5, omit Module View Diagram from SRS |
| User has NOT approved at Checkpoint #2 | LOOP - Return to Step 12.1 |
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
- [API-Derivation.md](<skill dir>/docs/API-Derivation.md) - API specification rules
- [Test-Case-Format.md](<skill dir>/docs/Test-Case-Format.md) - Test case encoding
- [Backend-Filtering.md](<skill dir>/docs/Backend-Filtering.md) - Backend relevance criteria
- [API-Definition-Structure.md](<skill dir>/docs/API-Definition-Structure.md) - Detailed API definition document template
- [Use-Case-Diagrams-Structure.md](<skill dir>/docs/Use-Case-Diagrams-Structure.md) - Use case diagrams document template

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

## 3. Filter for Back-End Relevant Requirements

Apply filtering criteria from [Backend-Filtering.md](<skill dir>/docs/Backend-Filtering.md):

### 3.1 Include Criteria (Requirements to KEEP)

Requirements are back-end relevant if they involve:

| Criterion | Examples |
|-----------|----------|
| **Data persistence** | Create, store, update, delete operations |
| **Business logic** | Validation rules, calculations, transformations |
| **Authorization** | Permission checks, role-based access |
| **External integrations** | API calls, event publishing/consuming |
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

## 5.5 Identify System Dependencies

After extracting entities and attributes, identify external systems and services that this module depends on.

### 5.5.1 Dependency Identification Patterns

Scan requirements for patterns indicating external dependencies:

| Pattern | Type | Example |
|---------|------|---------|
| "call [Service] API" | API | "call User Service API to validate user" |
| "invoke [Service]" | API | "invoke Profile Service to fetch details" |
| "query [Service]" | API | "query Organization Service for org data" |
| "consume [Event] event" | Event | "consume UserDeleted event from IAM" |
| "listen for [Event]" | Event | "listen for OrganizationUpdated events" |
| "receive [Event] from" | Event | "receive MembershipChanged from Group Service" |
| "fetch from [Service]" | API | "fetch user roles from Role Service" |
| "sync with [Service]" | API/Event | "sync membership data with B2B Service" |

### 5.5.2 Dependency Classification

| Type | Description | Characteristics |
|------|-------------|-----------------|
| **API** | Synchronous service-to-service calls | Real-time, blocking, requires availability |
| **Event** | Asynchronous event consumption | Eventually consistent, decoupled, resilient |

### 5.5.3 Dependency Documentation

Create a preliminary dependency table:

| # | System/Service | Type | Description | Source FS |
|---|----------------|------|-------------|-----------|
| 1 | User Service | API | Validate user exists and is active | GRP-FS-MEMB-001 |
| 2 | IAM Service | Event | Consume UserDeleted to cascade deletions | GRP-FS-MEMB-015 |
| 3 | Organization Service | API | Fetch organization details for validation | GRP-FS-CRUD-002 |

---

## CHECKPOINT #1.5: Dependency Approval (MANDATORY)

**⛔ STOP - Present dependencies and wait for user approval**

After identifying dependencies in Step 5.5, you MUST:

1. **Present the dependency table** to the user:

   ```markdown
   ## Identified Dependencies
   
   The following external systems/services have been identified as dependencies for this module:
   
   | # | System/Service | Type | Description | User Notes |
   |---|----------------|------|-------------|------------|
   | 1 | [Service Name] | API/Event | [Why this dependency exists] | |
   | 2 | [Service Name] | API/Event | [Why this dependency exists] | |
   ```

2. **Ask the user to review and approve:**
   - "Please review the identified dependencies above."
   - "You can add notes in the 'User Notes' column for any clarifications or concerns."
   - "Are these dependencies correct? Would you like to add, remove, or modify any?"

3. **Wait for explicit user approval** before proceeding to Step 6

4. **Incorporate user feedback:**
   - Add any dependencies the user identifies
   - Remove false positives
   - Record user notes in the final SRS document

### Decision Rules

| User Response | Action |
|---------------|--------|
| Approves dependencies | Proceed to Step 6 (Identify Event Types) |
| Requests additions | Add dependencies to table, re-present for approval |
| Requests removals | Remove dependencies, re-present for approval |
| Provides notes | Record notes, confirm, then proceed |
| Unclear response | Ask clarifying question, wait for response |

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

## 7. Derive API Interfaces

Follow rules in [API-Derivation.md](<skill dir>/docs/API-Derivation.md):

> **Note**: For REST API conventions (HTTP methods, path naming, error handling, pagination), refer to **api-skill**.

### 7.1 API Endpoint Classification

| Type | Path Prefix | Access | Example |
|------|-------------|--------|---------|
| **Internal** | /internal/ | Service-to-service only | /internal/system-roles |
| **Administrative** | /v2/ | Client-facing | /v2/custom-roles |
| **Admin** | /admin/ | Administrative access | /admin/roles |

### 7.3 API ID Encoding

API IDs follow a domain-prefixed pattern:

```
[DOMAIN]-API-[NUMBER]

Examples:
- GRP-API-001  (Group service, Internal API #1)
- GRP-API-101  (Group service, Administrative API #1)
- GRP-API-201  (Group service, Me API #1)
- ROLE-API-001 (Role service, Internal API #1)
```

**Numbering Conventions:**
- Internal APIs: 001-099
- Administrative APIs: 101-199
- Me APIs: 201-299

### 7.4 API Documentation Format

For each API endpoint, document:

```markdown
### [Operation Name]

- **Method**: [HTTP Method]
- **Path**: [Endpoint path]
- **Input**: [Request body/parameters]
- **Output**: [Response body]
- **Status Codes**:
  - 2XX: [Success scenarios]
  - 4XX: [Client error scenarios]
  - 5XX: [Server error scenarios]
```

---

## CHECKPOINT #2.5: Optional Artifacts Confirmation (MANDATORY)

**⛔ STOP - Ask user which optional artifacts to generate**

After deriving API interfaces (Step 7) and before generating SRS requirements, you MUST ask the user about optional artifacts:

1. **Present the optional artifacts menu:**

   ```markdown
   ## Optional Artifacts
   
   The following artifacts can be included in the SRS document. 
   They are **not generated by default** — please confirm which ones you'd like:
   
   1. **Test Cases** — Inline test cases (positive, negative, edge, security) for each requirement + Appendix B summary
   2. **Module View Diagram** — High-level architectural module view diagram (draw.io) showing system components and their interactions
   
   Would you like to generate:
   - Both? (test cases + module view)
   - Only test cases?
   - Only module view?
   - Neither? (SRS without test cases or module view)
   ```

2. **Wait for explicit user response**

3. **Record user choices** — these choices control Steps 9 and 9.5:
   - `generate_test_cases = true/false`
   - `generate_module_view = true/false`

### Decision Rules

| User Response | Action |
|---------------|--------|
| "both", "yes", "all" | Set both flags to `true`, proceed to Step 8 |
| "test cases", "only test cases" | Set `generate_test_cases = true`, `generate_module_view = false` |
| "module view", "only module view" | Set `generate_test_cases = false`, `generate_module_view = true` |
| "neither", "none", "skip" | Set both flags to `false`, proceed to Step 8 |
| Unclear response | Ask clarifying question, wait for response |

---

## 8. Generate SRS Requirements with FS Attribution

### 8.1 SRS Requirement Format

Each SRS requirement should follow this structure:

```markdown
### [SRS-ID] [Requirement Title]

- [Bullet point requirement statement]
- [Additional requirement detail]
- [Input/Output specification if applicable]

**Source FS**: [FS Requirement ID(s)]
```

### 8.2 ID Encoding

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

### 8.3 Attribution

Every SRS requirement MUST trace back to source FS requirements:

```markdown
**Test Cases:**
[...]

**Source FS Requirements:**
- GRP-FS-CRUD-001: The system shall allow users with Super Admin role to create groups.
- GRP-FS-CRUD-004: When a group is created, the system shall record...
```

---

## 9. Generate Test Cases (CONDITIONAL)

> **⚠️ CONDITIONAL**: This step is ONLY executed if `generate_test_cases = true` was set at Checkpoint #2.5. If the user declined test cases, **SKIP this entire section** and proceed to Step 9.5.

Follow rules in [Test-Case-Format.md](<skill dir>/docs/Test-Case-Format.md):

> **Parallel fan-out (≥3 SRS sections, advisory):** When generating test cases for ≥3 requirement sections, pre-allocate a disjoint test-case-ID range per section, then launch one Agent subagent per section **in a single message**. Each subagent generates test cases for its section only, staying within its ID range, and returns them as text. Main thread reconciles: merge, check ID continuity and no duplicates, ensure no duplicated cross-section scenarios, and verify cross-references to requirement IDs are consistent. Fall back to serial generation when fewer than 3 sections exist, sections share heavy context, or any subagent fails.

### 9.1 Test Case ID Encoding

```
[SRS-Requirement-ID]-[Type]-[Number]

Where Type:
- P = Positive test case (happy path)
- N = Negative test case (error handling)
- E = Edge case
- S = Security test case
```

Examples:
- `[SAB-ROLE-FR-1.0.0]-P-001` - First positive test for requirement 1.0.0
- `[SAB-ROLE-FR-1.0.0]-N-001` - First negative test for requirement 1.0.0

### 9.2 Test Case Structure

```markdown
**Test Cases:**

1. [SRS-ID]-P-001
   - Given [precondition]
   - Given [additional setup if needed]
   - [HTTP Method] [Endpoint] API call must return a [Status Code] status with [Expected Response]

2. [SRS-ID]-N-001
   - Given [failure precondition]
   - [HTTP Method] [Endpoint] API call must return a [Error Status] status with an `error.code: [ERROR_CODE]`
```

### 9.3 Standard Test Categories

For each CRUD operation, generate:

| Category | Test Type | Description |
|----------|-----------|-------------|
| **Create** | P-001 | Successful creation with valid input |
| | N-001 | Missing required fields |
| | N-002 | Data store failure |
| **Read** | P-001 | Successful retrieval |
| | N-001 | Resource not found |
| | N-002 | Data store failure |
| **Update** | P-001 | Successful update |
| | N-001 | Resource not found |
| | N-002 | Immutable field modification attempt |
| | N-003 | Data store failure |
| **Delete** | P-001 | Successful deletion with confirmation |
| | N-001 | Resource not found |
| | N-002 | Active dependencies prevent deletion |
| | N-003 | Missing confirmation |
| | N-004 | Data store failure |
| **Authorization** | N-0XX | Insufficient permissions (403) |
| | N-0XX | Out of scope access attempt |

---

## 9.5 Generate Module View Diagram (CONDITIONAL)

> **⚠️ CONDITIONAL**: This step is ONLY executed if `generate_module_view = true` was set at Checkpoint #2.5. If the user declined module view, **SKIP this section** and proceed to Step 10.

Generate a high-level module view diagram showing the system architecture:

### 9.5.1 Module Identification

From the extracted entities, APIs, events, and dependencies, identify:
- Core service modules (one per major entity or feature set)
- External dependency modules (from Checkpoint #1.5 approved dependencies)
- Event bus / messaging infrastructure
- Data store(s)

### 9.5.2 Diagram Generation

Create a draw.io module view diagram:
- Use the `create_new_diagram` MCP tool to generate the diagram
- Include modules as rounded rectangles with clear labels
- Show relationships between modules (API calls, event flows)
- Export as both `.drawio` (source) and `.svg` (for embedding)
- Save to: `<Project Root>/.data/requirements/diagrams/[DOMAIN]-module-view.drawio` and `.drawio.svg`

### 9.5.3 SRS Integration

When included, add the Module View Diagram section to the SRS document between "Source Feature Sets" and "Dependencies":

```markdown
## Module View Diagram

![Module View Diagram](./diagrams/[DOMAIN]-module-view.drawio.svg)

*Figure 1: Module view diagram showing system components and their interactions*

| Module | Responsibility | Dependencies |
|--------|----------------|--------------|
| [Module Name] | [Brief description] | [List of dependent modules] |
```

---

## 10. Identify Main Use Cases

Follow rules in [Use-Case-Diagrams-Structure.md](<skill dir>/docs/Use-Case-Diagrams-Structure.md):

### 10.1 Use Case Identification

Identify use cases from:
- CRUD operations for each entity (Create, Read, Update, Delete)
- Major user workflows spanning multiple operations
- Integration scenarios with external systems

### 10.2 Use Case ID Encoding

Use Case IDs follow a domain-prefixed pattern:

```
[DOMAIN]-UC-[NUMBER]

Examples:
- GRP-UC-001  (Group service, Use Case #1)
- GRP-UC-002  (Group service, Use Case #2)
- ROLE-UC-001 (Role service, Use Case #1)
```

### 10.3 Use Case Documentation

For each use case, document:

| Field | Description |
|-------|-------------|
| UC ID | Unique identifier ([DOMAIN]-UC-001, [DOMAIN]-UC-002, etc.) |
| Name | Descriptive use case name |
| Primary Actor | Main actor performing the use case |
| Preconditions | What must be true before execution |
| Postconditions | What is true after successful execution |
| Main Success Scenario | Happy path steps |
| Alternative Scenarios | Variations from main flow |
| Exception Scenarios | Error handling flows |

### 10.4 Use Case Summary Table

Create the summary table for the SRS Main Use Cases section:

```markdown
| UC ID | Use Case Name | Primary Actor | Description |
|-------|---------------|---------------|-------------|
| [DOMAIN]-UC-001 | Create [Entity] | [Actor] | [Brief description] |
| [DOMAIN]-UC-002 | Update [Entity] | [Actor] | [Brief description] |
| [DOMAIN]-UC-003 | Delete [Entity] | [Actor] | [Brief description] |
```

---

## 11. Quality Check and Validation

### 11.1 Completeness Check

Verify:
- [ ] All back-end relevant FS requirements are addressed
- [ ] All entities have complete attribute lists
- [ ] All operations have corresponding API endpoints
- [ ] *(If `generate_test_cases = true`)* All requirements have test cases (at least P-001 and N-001)
- [ ] *(If `generate_module_view = true`)* Module View Diagram is included with module descriptions
- [ ] All SRS requirements have FS attribution

### 11.2 Consistency Check

Verify:
- [ ] ID encoding follows conventions
- [ ] API paths follow REST conventions
- [ ] Error codes are consistent
- [ ] Status codes match HTTP standards

### 11.3 Traceability Check

Verify:
- [ ] Every SRS requirement traces to at least one FS requirement
- [ ] No orphaned SRS requirements
- [ ] Attribution is accurate

### 11.4 Structural Provenance Check (Companion-Doc Refinement)

Before proposing any new companion-document structure (entity, table, event, enum, API, field, or use-case phase), verify against the source SRS and record explicit line anchors in the iteration plan.

For every proposed addition or change, the plan MUST cite:
- The exact `file_path:line-line` anchor(s) in the SRS proving the artifact already exists
- What form the SRS gives it: **canonical entity/event/API/enum**, **schema-level field on an existing artifact**, or **prose-only obligation/gate on existing flow**
- Whether the companion-doc change is a **materialization of existing structure** or only a **documentation note / test / use-case annotation**

Verify:
- [ ] Every proposed structural change cites SRS line anchors
- [ ] The cited anchors prove the artifact's form, not just a related concept
- [ ] Prose-only obligations are not materialized as new entities/tables/events/APIs/enums
- [ ] Schema-level fields on existing outputs are not escalated into entity-model or storage-model additions unless the SRS explicitly says so
- [ ] If the SRS says no new entity/event/API/enum is introduced, the plan preserves that invariant explicitly

If no SRS anchor can prove the artifact already exists in the proposed form, DO NOT propose it as new structure. Instead, either:
1. render it as a note/constraint on an existing artifact already named by the SRS, or
2. flag it as an unsupported assumption requiring SRS revision rather than companion-doc invention.

---

## 12. Iterative Refinement Loop (MANDATORY CHECKPOINT #2)

> **⛔ CRITICAL**: This section is MANDATORY. You MUST NOT skip to Section 13 without completing at least one full iteration and receiving explicit user confirmation.

### 12.1 Present Draft and Ask for Feedback (REQUIRED)

**⛔ STOP - Present SRS and wait for user response**

After generating the SRS in steps 3-10, you MUST:

1. **Present the draft SRS** to the user (in a readable format, not written to file yet)
2. **Self-analyze** the generated SRS for:
   - Missing test cases or edge cases
   - API inconsistencies
   - Entity attribute gaps
   - Authorization scenarios not covered
   - Event handling gaps
3. **Provide improvement suggestions** to the user
4. **Ask explicitly**: "Would you like to make any changes, additions, or refinements to this SRS?"
5. **Wait for user response** - Do NOT proceed until user responds

### 12.2 Generate New Version (if changes requested)

Based on user feedback:
- Indicate what changed from the previous version
- Use **Added**, **Modified**, **Removed** markers

### 12.3 Validation Against Source FS

Cross-reference every SRS requirement against source FS:
- Verify FS reference is accurate
- Ensure SRS correctly interprets FS intent
- Flag any SRS requirements without FS backing

### 12.4 Confirmation Checkpoint (REQUIRED)

**⛔ STOP - Explicit confirmation required before proceeding**

Ask the user: **"Are you satisfied with this SRS, or would you like further refinements?"**

- **If user says NO**: Return to step 12.1
- **If user says YES**: Proceed to step 13

### 12.5 Single Refinement Mode (ALTERNATIVE)

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
   - Show the affected requirement(s), test case(s), or section(s) in full
   - Briefly describe what was changed

4. **Ask continuation question:**
   
   **"Refinement applied. Would you like to:**
   - **Provide another refinement instruction?**
   - **Finalize and write to file?"**

5. **Decision handling:**
   - **If user provides another refinement** → Return to step 1
   - **If user says "finalize", "done", "write", "save"** → Proceed to Section 13

**Example interaction:**
```
User: "Add a negative test case for SAB-GRP-FR-2.1.0 when group name exceeds limit"

Agent: "Refinement applied:

**Added: Test Case [SAB-GRP-FR-2.1.0]-N-002**

2. [SAB-GRP-FR-2.1.0]-N-002
   - Given a user with valid permissions
   - Given a group name exceeding 200 characters
   - POST /v2/groups API call must return a 400 status with an `error.code: INVALID_GROUP_NAME`

Would you like to:
- Provide another refinement instruction?
- Finalize and write to file?"

User: "Change the error code to NAME_TOO_LONG"

Agent: "Refinement applied:

**Modified: Test Case [SAB-GRP-FR-2.1.0]-N-002**
- Before: `error.code: INVALID_GROUP_NAME`
- After: `error.code: NAME_TOO_LONG`

Would you like to:
- Provide another refinement instruction?
- Finalize and write to file?"

User: "finalize"

Agent: → Proceeds to Section 13 (Write to file)
```

---

## 13. Write SRS Document to File

### 13.1 Output Location

Write to: `<Project Root>/.data/requirements/[Domain]-SRS-[Version].md`

Example: `.data/requirements/Role-Management-SRS-2.0.md`

### 13.2 Document Structure

Follow template in [SRS-Structure.md](<skill dir>/docs/SRS-Structure.md):

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

## API Reference

| Operation | Method | Path | Description |
|-----------|--------|------|-------------|
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

[Requirements and test cases]

---

## Appendix A: FS-to-SRS Traceability

| SRS ID | FS ID(s) | Description |
|--------|----------|-------------|
| ... | ... | ... |

## Appendix B: Test Case Summary

| SRS ID | Total Tests | Positive | Negative | Edge | Security |
|--------|-------------|----------|----------|------|----------|
| ... | ... | ... | ... | ... | ... |
```

---

## 14. Generate Companion Documents

After writing the main SRS document, generate the companion documents:

> **Parallel fan-out (companion documents):** After the SRS file is written, generate the API-Definition document and the Use-Case-Diagrams document via two Agent subagents launched **in a single message**. Each subagent receives the written SRS file path and its target artifact type, and writes its draft to a unique temp path (never the final destination). Main thread reconciles: verify both drafts cite consistent SRS section anchors, resolve any mismatch, then move the drafts to their final destinations. If either subagent fails, generate both documents serially, writing directly to final paths. This fan-out must only start after the SRS write completes; all user checkpoints stay in the main conversation.

### 14.1 API Definition Document

Create: `<Project Root>/.data/requirements/[Domain]-API-Definition-[Version].md`

Follow template in [API-Definition-Structure.md](<skill dir>/docs/API-Definition-Structure.md):

**Contents:**
- Document Information (linked to SRS)
- API Overview (categories, authentication, common headers)
- Internal APIs (full specifications)
- Administrative APIs (full specifications)
- Common Data Types
- Error Response Format
- Pagination, Filtering, Sorting patterns

**Extraction from SRS:**
- Copy API Reference entries and expand with full details
- Add request/response schemas based on Entity Reference
- Include examples for each endpoint
- Link each API back to source SRS requirements
- For any companion-doc refinement pass, cite the exact SRS line anchors proving whether each proposed artifact is an API/entity/enum, a schema-level field on an existing output contract, or only a prose obligation on an existing flow before adding structure
- If the cited SRS anchor renders the requirement as schema-level or prose-only, reflect it as a schema note / validation note / use-case annotation / test case rather than inventing a new entity, table, event, endpoint, or phase

**Iteration-plan rule (mandatory):**
Before applying a companion-doc refinement plan, include a short provenance table with columns: `Proposed change`, `SRS anchor`, `Artifact form in SRS`, `Allowed companion-doc rendering`.

Example forms:
- `schema-level field on existing output` → schema note / typed-contract update / test coverage
- `prose-only obligation` → gate note / use-case step / validation rule / test coverage
- `canonical entity/API/event/enum` → normal structural companion-doc rendering

### 14.2 Use Case Diagrams Document

Create: `<Project Root>/.data/requirements/[Domain]-Use-Case-Diagrams-[Version].md`

Follow template in [Use-Case-Diagrams-Structure.md](<skill dir>/docs/Use-Case-Diagrams-Structure.md):

**Contents:**
- Document Information (linked to SRS)
- Use Case Index
- Actor Definitions
- Detailed use case specifications for each UC from SRS
- PlantUML sequence diagrams

**For each use case:**
1. Copy use case summary from SRS Main Use Cases section
2. Expand with full scenario details:
   - Main Success Scenario (numbered steps)
   - Alternative Scenarios
   - Exception Scenarios
3. Create PlantUML sequence diagram using ```plantuml code blocks
4. Include all participants, message flows, and alternative/exception fragments

### 14.3 PlantUML Sequence Diagram Format

For syntax rules, elements, note colors, and a worked example, see [PLANTUML.md](PLANTUML.md).
