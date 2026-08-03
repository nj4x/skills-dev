---
name: FS-skill
description: Author or revise Feature-Set (FS) requirements in EARS format. For SRS documents from existing FS, use SRS-skill instead.
disable-model-invocation: true
---

# FS Skill

This skill helps with requirements engineering using the EARS (Easy Approach to Requirements Syntax) methodology. It can be used for:
- Writing new requirements from source documents or user input
- Modifying or updating existing requirements
- Analyzing requirements for contradictions (conflicts, inconsistencies, conflicting requirements) or gaps
- Converting informal requirements to EARS format

---

## 0. Confirm Skill Activation

Briefly explain what you'll do and ask the user: "Would you like me to use the FS skill for this task?" Proceed once the user confirms (e.g., "yes", "go ahead"). Skip if the user's task explicitly mentions "use EARS" or invokes this skill directly.

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

### 3.1 Initialize Source Document Access

When a source path is provided, use MCP semantic search tools first; fall back to `list_files`/`read_file` only when MCP is unavailable.

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
If an MCP tool call fails, ask the user to reconnect the `mcp-vectors` server in Claude Code's MCP settings and confirm when ready before retrying.

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

## 7. Iterative Refinement Loop

### 7.1 Present Draft and Ask for Feedback

1. **Present the draft requirements** to the user (in a readable format, not written to file yet)
2. **Self-analyze** the generated requirements for:
   - Ambiguity or unclear language
   - Missing edge cases or error conditions
   - Requirements that could be more specific
   - Gaps in coverage based on source documents
3. **Block finalization** for any new or materially edited requirement that defines an invocation or realization mechanism; rewrite it to an outcome, capability, lifecycle behavior, or safety constraint.
4. **Provide improvement suggestions** to the user
5. **Ask explicitly**: "Would you like to make any changes, additions, or refinements to these requirements?"
6. Proceed only after the user responds

### 7.2 Generate New Version (if changes requested)

Clearly indicate what changed using:
- **Added**: New requirements
- **Modified**: Changed requirements (show before/after)
- **Removed**: Deleted requirements

### 7.3 Validation Phase

Follow [Validation-Process.md](<skill dir>/docs/Validation-Process.md) for:
- Creating validation plan
- Executing validation with MCP search
- Recording validation results (✓ Validated, ⚠ Partial, ✗ Not Found, ⚡ Contradicts)
- Applying enforcement rules

**Progressive Source Discovery:** Track `file_path` values from search results in a "Processed Sources" list. When validating subsequent requirements or seeking additional evidence, use the `exclude_files` parameter to skip already-processed documents and discover new source materials:

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

This progressively discovers all relevant documents rather than repeatedly finding the same top matches.

**Parallel fan-out (≥3 requirement groups, advisory):** Fan out MCP evidence searches across one Agent subagent per requirement group, launched in a single message. The `exclude_files` progressive chain is maintained *within* each group's subagent (never across subagents). Main thread reconciles evidence tables across groups and checks for cross-group coverage gaps. Fall back to serial validation when fewer than 3 groups exist or any subagent fails.

### 7.4 Quality Re-check

- Re-verify remaining requirements against source documents
- Ensure all updates align with EARS syntax
- Check for new contradictions (conflicts, inconsistencies) introduced by changes

### 7.5 Confirmation Checkpoint

Ask the user: **"Are you satisfied with these requirements, or would you like further refinements?"**

- **If user says NO, wants changes, or provides feedback**: Return to step 7.1
- **If user explicitly says YES, satisfied, approved, or similar**: Proceed to step 8

Write to file only after receiving explicit user confirmation at this checkpoint.

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