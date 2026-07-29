---
name: FS-skill
description: Assists with requirements engineering tasks including writing, reviewing, analyzing, generating, or modifying Feature Set (FS) requirements using EARS methodology. Use this skill when user asks to build, write, create, generate, analyze, review, or modify requirements, requirements documents, or feature set (FS) specifications from source documents. This skill produces EARS-formatted feature requirements. For creating SRS (Software Requirements Specification) documents from existing FS requirements, use the FS-to-SRS skill instead. This skill REQUIRES user confirmation at multiple checkpoints before completion.
disable-model-invocation: true
---

# FS Skill

> **⚠️ IMPORTANT**: This skill has MANDATORY confirmation checkpoints. Do NOT write final requirements to file until user explicitly confirms satisfaction in the Iterative Refinement Loop (Section 6).

This skill helps with requirements engineering using the EARS (Easy Approach to Requirements Syntax) methodology. It can be used for:
- Writing new requirements from source documents or user input
- Modifying or updating existing requirements
- Analyzing requirements for contradictions (conflicts, inconsistencies, conflicting requirements) or gaps
- Converting informal requirements to EARS format

---

## Workflow Summary with Checkpoints

### Phase 1: Initialization (BLOCKING)
1. **CHECKPOINT #1** - Confirm skill activation (Section 0)
   - Action: Ask user to confirm FS skill usage
   - Condition: WAIT for explicit user confirmation
   - If user activated via `use_skill` → Skip to Phase 2

### Phase 2: Research & Generation
2. **Step 1** - Read EARS syntax documentation
3. **Step 2** - Analyze existing requirements
4. **Step 3** - Identify categories and groupings
5. **Step 4** - Generate requirements in EARS format
6. **Step 5** - Quality check and document contradictions (conflicts, inconsistencies)

### Phase 3: Iterative Refinement Loop (BLOCKING)
7. **CHECKPOINT #2** - Begin refinement loop (Section 6)
   - Present draft requirements + improvement suggestions
   - IF user requests changes → Incorporate feedback
   - Execute mandatory validation phase
   - Ask user: "Are you satisfied with these requirements?"
     - IF NO → Continue loop
     - IF YES → Proceed to Phase 4

### Phase 4: Finalization
8. **Step 7** - Write requirements to file (ONLY after explicit user approval)

### Decision Rules
| Condition | Action |
|-----------|--------|
| User has NOT confirmed at Checkpoint #1 | WAIT - Do not proceed |
| User has NOT approved at Checkpoint #2 | LOOP - Return to refinement |
| User says "yes", "approved", "satisfied", "proceed" | PROCEED to next phase |
| User provides feedback or says "no" | INCORPORATE changes, stay in loop |

---

## 0. Confirm Skill Activation (MANDATORY CHECKPOINT #1)

**⛔ STOP - Do not proceed without user confirmation**

Before proceeding with ANY requirements work:
1. Ask the user: "I can help with requirements using EARS format. Would you like me to use the FS skill for this task?"
2. Briefly explain what the skill will do based on their request
3. **Wait for explicit user confirmation** (e.g., "yes", "proceed", "go ahead")
4. Only after receiving confirmation, proceed to step 1

> **Note**: If user's task explicitly mentions "use EARS" or activates this skill via `use_skill`, this checkpoint is satisfied.

---

## 1. Understand the EARS Syntax

Read [EARS.md](<skill dir>/docs/EARS.md) to understand the EARS syntax.

---

## 2. Using MCP Semantic Search (RECOMMENDED)

Read [MCP-Usage.md](<skill dir>/docs/MCP-Usage.md) for detailed MCP tool usage including:
- Available MCP tools (`index_files`, `search_documents`, `list_indexed_files`)
- Indexing approval process
- Mandatory search triggers
- MCP connection recovery

---

## 3. Analyze Existing and New Requirements

### 3.1 Initialize Source Document Access (MANDATORY CHECKPOINT)

> **⛔ PROHIBITED**: Do NOT use `list_files` or `read_file` to explore source directories when a source path is provided. ALWAYS use MCP semantic search tools first.

**Decision Tree:**

```
IF user request contains a source directory path (e.g., `/Users/.../FeatureSets_v2.0`)
  → Step A: IMMEDIATELY call `list_indexed_files` with base_dirs=[source_directory]
  → Step B: IF files are indexed → Proceed to Section 3.2 using `search_documents`
  → Step C: IF files are NOT indexed → Ask user for indexing approval:
      "Would you like me to index the source documents at `<PATH>` for semantic search?
       This enables more accurate content discovery.
       Options: 1. Yes, index  2. No, check existing  3. Skip indexing"
      → IF user approves → Call `index_files`, then proceed to Section 3.2
      → IF user declines → Use `read_file` on individual files (fallback only)

IF user request does NOT contain a source directory path
  → Use `read_file` and `search_files` as fallback methods
```

**MCP Connection Recovery:**
If MCP tool call fails, ask user: "The MCP server `mcp-vectors` appears disconnected. Please reconnect it in Cline's MCP Servers settings, then let me know when ready." Wait for user confirmation before retrying or falling back.

See [MCP-Usage.md](<skill dir>/docs/MCP-Usage.md) for additional MCP tool details.

### 3.2 Explore and Analyze

- Use `search_documents` to explore source documents with natural language queries
- Analyze existing requirements in the requirements directory
- Determine if user input should be treated as new requirements or modifications

---

## 4. Identify Categories

Read `engineering/setup-lineage/SKILL.md` → [Requirements boundary](../../engineering/setup-lineage/SKILL.md#requirements-boundary). Draft only outcomes, capabilities, lifecycle behavior, and material safety constraints; rewrite invocation mechanisms as observable constraints and route their realization to an ADR.

Follow rules in [Categorization.md](<skill dir>/docs/Categorization.md) for:
- Requirement type classification (FS vs SRS)
- Category acronym conventions
- Grouping guidelines

---

## 5. Generate Requirements

### 5.1 Format Requirements

Follow [Requirement-Format.md](<skill dir>/docs/Requirement-Format.md) for:
- Table format (ID, Requirement, Source columns)
- ID encoding conventions
- Source reference format (including `generate_wiki_link` MCP tool)
- Local path tracking

### 5.2 Apply EARS Syntax

Generate requirements following EARS syntax from [EARS.md](<skill dir>/docs/EARS.md). Requirements can be rephrased from user inputs for better clarity.

### 5.3 Stable-ID Immutability

Once an FS ID (e.g., `GRP-FS-CRUD-001`) is written to file and confirmed by the user, that ID is **immutable**. Renaming an ID equals deletion + re-creation; apply the deletion guard (Section 9) against the old ID before removing it.

### 5.4 Parallel Fan-Out (advisory)

**Parallel fan-out (≥3 categories, advisory):** When requirements span ≥3 independent categories, pre-allocate a disjoint requirement-ID range to each category (e.g. 001–049, 050–099) so IDs never collide, then launch one Agent subagent per category **in a single message** (parallel execution). Each subagent receives the source-document pointers, the EARS rules, its category scope, and its ID range; it returns drafted requirements as text and must not write files. After all report back, reconcile: merge drafts, check ID continuity and no duplicates, deduplicate cross-cutting requirements, unify terminology, resolve cross-references — then run the quality check on the merged set. The ≥3 threshold is a floor, not a mandate: fall back to serial main-thread generation when categories share heavy context, fewer than 3 exist, or any subagent fails or returns empty. User checkpoints and file writes always stay in the main conversation.

---

## 6. Quality Check

Follow [Quality-Check.md](<skill dir>/docs/Quality-Check.md) for:
- Validation with semantic search
- Accuracy verification
- Contradiction documentation format

---

## 7. Iterative Refinement Loop (MANDATORY CHECKPOINT #2)

> **⛔ CRITICAL**: This section is MANDATORY. You MUST NOT skip to Section 8 without completing at least one full iteration and receiving explicit user confirmation.

### 7.1 Present Draft and Ask for Feedback (REQUIRED)

**⛔ STOP - Present requirements and wait for user response**

1. **Present the draft requirements** to the user (in a readable format, not written to file yet)
2. **Self-analyze** the generated requirements for:
   - Ambiguity or unclear language
   - Missing edge cases or error conditions
   - Requirements that could be more specific
   - Gaps in coverage based on source documents
3. **Block finalization** for any new or materially edited requirement that defines an invocation or realization mechanism; rewrite it to an outcome, capability, lifecycle behavior, or safety constraint.
4. **Provide improvement suggestions** to the user
5. **Ask explicitly**: "Would you like to make any changes, additions, or refinements to these requirements?"
6. **Wait for user response** - Do NOT proceed until user responds

### 7.2 Generate New Version (if changes requested)

Clearly indicate what changed using:
- **Added**: New requirements
- **Modified**: Changed requirements (show before/after)
- **Removed**: Deleted requirements

### 7.3 Validation Phase (MANDATORY)

Follow [Validation-Process.md](<skill dir>/docs/Validation-Process.md) for:
- Creating validation plan
- Executing validation with MCP search
- Recording validation results (✓ Validated, ⚠ Partial, ✗ Not Found, ⚡ Contradicts)
- Applying enforcement rules

**Progressive Source Discovery (REQUIRED):**
During validation, track `file_path` values from search results in a "Processed Sources" list. When validating subsequent requirements or seeking additional evidence, use the `exclude_files` parameter to skip already-processed documents and discover NEW source materials:

```
# First search
results1 = search_documents(query="group name validation")
processed_sources = [r.file_path for r in results1]

# Subsequent search - exclude already-analyzed sources to find NEW documents
results2 = search_documents(
    query="group name character limits",
    exclude_files=processed_sources
)
processed_sources.extend([r.file_path for r in results2])
```

This ensures comprehensive source coverage by progressively discovering all relevant documents rather than repeatedly finding the same top matches.

**Parallel fan-out (≥3 requirement groups, advisory):** Fan out MCP evidence searches across one Agent subagent per requirement group, launched in a single message. The `exclude_files` progressive chain is maintained *within* each group's subagent (never across subagents). Main thread reconciles evidence tables across groups and checks for cross-group coverage gaps. Fall back to serial validation when fewer than 3 groups exist or any subagent fails.

### 7.4 Quality Re-check

- Re-verify remaining requirements against source documents
- Ensure all updates align with EARS syntax
- Check for new contradictions (conflicts, inconsistencies) introduced by changes

### 7.5 Confirmation Checkpoint (REQUIRED)

**⛔ STOP - Explicit confirmation required before proceeding**

Ask the user: **"Are you satisfied with these requirements, or would you like further refinements?"**

- **If user says NO, wants changes, or provides feedback**: Return to step 7.1
- **If user explicitly says YES, satisfied, approved, or similar**: Proceed to step 8

> **⚠️ BLOCKING RULE**: Do NOT use `write_to_file` or `attempt_completion` until you have received an explicit positive confirmation from the user at this checkpoint.

### 7.6 Single Refinement Mode (ALTERNATIVE)

**Trigger phrases**: "refine", "one by one", "checkpoint after each", "iterative refinement"

When user requests iterative refinement with individual checkpoints:

1. Wait for user's single refinement instruction
2. Apply ONLY the requested change
3. Present checkpoint showing specific change (before/after)
4. Ask: "Refinement applied. Would you like to provide another refinement instruction, or finalize and write to file?"
5. If user provides another refinement → Return to step 1
6. If user says "finalize", "done", "write" → Proceed to Section 8

---

## 8. Write Requirements to File

Follow [Document-Template.md](<skill dir>/docs/Document-Template.md) for:
- Required document structure
- Required sections (Header, Source Documents, Contradictions, Requirements, Appendices)
- Output location and file naming conventions

Every FS document written by this skill must include the following YAML frontmatter block at the top of the file:

```yaml
---
artifact-type: fs
lineage-rules: root
---
```

---

## 9. Deletion Guard

Before deleting or renaming (= deleting + re-creating) any FS requirement ID:

### 9.1 Scan SRS Documents

Scan all SRS documents matching `.data/requirements/*-SRS-*.md` for references of the form `**Source FS**: <ID>`.

Surface the scan scope report before blocking or permitting deletion:
- Paths searched: `.data/requirements/*-SRS-*.md`
- Files found: `<N>` files
- Matches found: `<M>` references to `<ID>`

### 9.2 Block on Orphans

If any SRS items reference the FS ID being deleted:
- **Block** the deletion.
- Surface the full list of orphaned SRS items (file path + requirement ID + current `**Source FS**:` value).
- Require the user to re-anchor each orphaned SRS item to another valid FS ID, or delete the orphaned SRS item, before proceeding.
- Re-run the scan after each re-anchoring until the reference count reaches zero.

### 9.3 Permit Deletion

Only after the scan confirms zero remaining references to the FS ID may deletion proceed.