# Validation Process Guide

> **⛔ CRITICAL**: Every requirement MUST be validated against source documents or user input. This step cannot be skipped.

The validation phase ensures all generated requirements have traceable support in source materials. Requirements without support **shall be removed**; requirements with partial support **shall be updated**.

---

## 1. Create Validation Plan

Before executing validation, create a checklist of all requirements to validate:

```markdown
## Validation Plan

| # | Requirement ID | Requirement Summary | Search Query |
|---|----------------|---------------------|--------------|
| 1 | GRP-FS-NAME-001 | Group name max 200 chars | "group name length characters limit" |
| 2 | GRP-FS-NAME-002 | Special characters allowed | "group name special characters allowed" |
| ... | ... | ... | ... |
```

---

## 1.5 Pre-Analysis: Detecting Removed Features in Source Documents

> **⚠️ IMPORTANT**: Before generating or validating requirements, scan source documents for **strikethrough text** (`~~text~~` in Markdown). Struck-through content represents features or requirements that have been **explicitly removed** from the spec and must NOT appear in the requirements output.

### What Strikethrough Means

In Confluence/Markdown source documents, `~~text~~` (rendered as ~~text~~) indicates:
- A feature, field, or behavior that has been **deprecated or removed** in this version
- Content that was present in a prior version but is **no longer part of the spec**
- Items explicitly excluded by the product team during the source document review

### How to Handle Strikethrough Content

| Strikethrough Scenario | Action |
|------------------------|--------|
| A field/option is struck through (e.g., `~~Grade~~`, `~~Role~~`) | Do NOT include that field in any requirement |
| An entire workflow step is struck through | Treat the step as removed; do not generate a requirement for it |
| A role/actor name is struck through (e.g., `~~Group Admin~~`) | Exclude that actor from the requirement's subject |
| A requirement already exists for struck-through content | **Remove** the requirement (preserve ID gap — do not renumber) |
| An inconsistency exists (struck through in one source but not another) | Add a **CONTR-NNN** entry to the Contradictions table with Impact: Open |

### Strikethrough Detection Checklist

When reading source documents, explicitly check for `~~`:
- [ ] In field/attribute lists (optional or mandatory fields)
- [ ] In workflow steps / numbered process flows
- [ ] In sub-items within workflow steps (partial strikethrough — some bullets removed while others remain active)
- [ ] In table rows (e.g., column definitions, filter options)
- [ ] In role/actor mentions in permission or access sections
- [ ] In UX flow descriptions (buttons, menu items, options)

### Example

```markdown
Source document excerpt:
  Optional fields: Middle Name, ~~Grade~~, ~~Class~~, ~~Department~~

Correct interpretation:
  → Optional fields: Middle Name only
  → Grade, Class, Department must NOT appear in requirements
  → Any existing requirement referencing Grade/Class/Department → REMOVE (preserve ID gap)
```

### Partial Strikethrough Within Workflow Steps

> **⚠️ COMMON PITFALL**: A single workflow step can contain a mix of struck-through and active sub-items. Only the non-struck content is authoritative. Do NOT generate requirements from the struck-through portions, even if they appear within an otherwise valid step.

**Process:**

1. **Read the entire step** including all sub-items
2. **Extract only the non-struck content** — struck-through bullets are removed features
3. **Cross-reference other steps** — look for steps that describe the actual behavior for the removed feature (e.g., Step 3 may describe what happens instead of the struck validation in Step 7)

**Decision Table:**

| Scenario | Action |
|----------|--------|
| Step has mixed struck/active bullets (e.g., `~~2SV check~~` struck but `Group type check` active) | Generate requirements ONLY from active (non-struck) bullets |
| Step N describes behavior ("assignment completes normally") while Step M has struck-through validation for the same feature | Step N is authoritative; do NOT derive a blocking/validation requirement from the struck content in Step M |
| A general policy statement exists (e.g., "2SV is mandatory for admins") but the enforcement mechanism is struck through | The policy is informational context, NOT a basis for an enforcement requirement — add a **Note** referencing the policy if a replacement requirement exists |

**Example — Partial Strikethrough in a Validation Step:**

```markdown
Source document (Role Assignment v2.0):

Step 3: "When assigning an admin role to a user whose 2SV is off,
         the role assignment is completed normally.
         However, an error occurs due to the access level when calling
         APIs related to admin privileges."

Step 7: "When assigning roles to users or groups, the following
         validations are performed:
         * ~~User: 2SV setup status~~
             + ~~Check if 2SV is disabled for each User~~
             + ~~If there is no User level setting (null), check OU policy~~
             + ~~If 2SV is off, display error and notify 2SV setup is required~~
         * Group: Check if the Group type is a 'Role-assign group'
             + Only 'Role-assign group' type is allowed
             + Super admin roles cannot be assigned to groups"

Correct interpretation:
  → Step 7 2SV validation is entirely struck through → REMOVED
  → Step 3 describes the actual 2SV behavior → role assignment completes normally
  → Generate requirement from Step 3 (assignment completes), NOT from struck Step 7
  → Generate requirement from Step 7 Group-type validation (active content)
  → Do NOT generate: "system shall verify 2SV" or "system shall block if 2SV off"
```

---

## 1.6 Pre-Analysis: Detecting "Out of Scope" Content in Source Documents

> **⚠️ IMPORTANT**: Before generating or validating requirements, check source document **metadata headers** for "Out of X.Y scope" markers. Content under such markers represents features **excluded from the target version** and must NOT appear in the requirements output.

### What "Out of Scope" Means

In Confluence source documents, the **Versions** metadata row (or section headers) may contain:
- A struck-through version marker followed by "Out of X.Y scope" (e.g., `~~true Yellow 2.0~~ → Out of 2.0 scope`)
- An explanatory note describing why the feature is excluded (e.g., "Account client integration is out of scope of V2.0 schedule")

This indicates the **entire page** (or section) is excluded from the specified version.

### How to Handle "Out of Scope" Content

| Scenario | Action |
|----------|--------|
| Page-level "Out of X.Y scope" matching the target version | **Skip the entire page** — do not generate any requirements from it |
| Section-level "Out of scope" header | **Skip that section only** — content outside the section may still be valid |
| Struck-through version marker WITHOUT "out of scope" text | **Check remaining content** — the page may still contain valid requirements |
| "Out of scope" for a **different** version (e.g., "Out of 1.0 scope" when building 2.0 requirements) | **Page may still be in scope** — verify against the target version |

### "Out of Scope" Detection Checklist

When reading source documents, check for scope exclusion markers in:
- [ ] The **Versions** row in the page metadata table
- [ ] Section headers or subheadings (e.g., "Out of V2.0 Scope")
- [ ] Bold or emphasized text near version markers
- [ ] Explanatory notes following struck-through entries

### Example

```markdown
Source document (Forced device sign-out v2.0, Page 1761210418):

Metadata table:
  | Versions | ~~true Yellow 2.0~~ → Out of 2.0 scope
  |          | **Account client integration is out of scope of V2.0 schedule,
  |          | so "sign-out on the device" is also excluded from the 2.0 scope.**

Correct interpretation:
  → Entire page is out of V2.0 scope
  → Do NOT generate any requirements from this page for V2.0
  → If requirements already exist referencing this page → REMOVE (preserve ID gap)
  → Document the exclusion reason if relevant to other features
```

---

## 2. Execute Validation

For each requirement in the validation plan:

### 2.1 Search with MCP
Use MCP `search_documents` tool to search indexed source documents:
- Use the requirement's key concepts as the query
- Include synonyms and related terms
- Be specific but not too narrow

**Iterative Source Discovery Pattern (REQUIRED):**

To ensure comprehensive source coverage rather than repeatedly finding the same documents:

1. **Initialize tracking**: Create a "Processed Sources" list at the start of validation
2. **First search**: Execute `search_documents` with your query
3. **Record sources**: Add all `file_path` values from results to the Processed Sources list
4. **Subsequent searches**: Pass the Processed Sources list to `exclude_files` parameter
5. **Repeat until exhausted**: Continue until searches return no new relevant sources

```
# Example workflow
processed_sources = []

# First requirement validation
results = search_documents(query="user authentication requirements")
processed_sources.extend([r["file_path"] for r in results["results"]])

# Second requirement validation - discover NEW sources
results = search_documents(
    query="password policy requirements",
    exclude_files=processed_sources  # Skip already-analyzed documents
)
processed_sources.extend([r["file_path"] for r in results["results"]])

# Continue pattern for remaining requirements...
```

This progressive discovery approach:
- Prevents the same high-ranking documents from dominating all search results
- Uncovers requirements evidence across a broader set of source documents
- Ensures complete source document coverage during validation

### 2.2 Interpret Search Results
- Check relevance scores (higher = better match)
- Read the matched text chunks for exact wording
- Note the source file path for the Source column
- If no results, try alternative queries before marking as "Not Found"

### 2.3 User-Provided Requirements
For user-provided requirements: Review the original user input to confirm the requirement was explicitly requested

### 2.4 Record Evidence
Record the evidence found (or lack thereof) for each requirement

---

## 3. Record Validation Results

Document validation results in a table with the following statuses and **mandatory actions**:

| Status | Symbol | Meaning | **Mandatory Action** |
|--------|--------|---------|----------------------|
| Validated | ✓ | Exact or strong match found in source | **Keep** requirement as-is |
| Partial | ⚠ | Related content found but differs | **Update** requirement to match source |
| Not Found | ✗ | No supporting evidence in sources | **Remove** requirement |
| Contradicts | ⚡ | Source says opposite or conflicts with another requirement | **Escalate** as contradiction |

### Validation Results Table Format

| Requirement ID | Status | Evidence | Action Taken |
|----------------|--------|----------|--------------|
| GRP-FS-NAME-001 | ✓ Validated | "Allowed length: 200 characters" (chunk 26) | Kept |
| GRP-FS-NAME-002 | ⚠ Partial | Source lists different special chars | **Updated** to match source |
| GRP-FS-NAME-003 | ✗ Not Found | No matching content found | **Removed** |
| GRP-FS-NAME-004 | ⚡ Contradicts | Source explicitly allows this | **Escalated** to CONTR-003 |

---

## 4. Apply Validation Results

### Enforcement Rules

1. **Remove unsupported requirements**: If validation status is "Not Found" (✗), the requirement **shall be removed** from the specification. Document removal in change tracking.

2. **Update partial requirements**: If validation status is "Partial" (⚠), the requirement **shall be updated** to accurately reflect source document content. Show before/after in change tracking.

3. **Escalate contradictions (conflicts, inconsistencies)**: If validation status is "Contradicts" (⚡), add a new entry to the Contradictions table and mark requirement for stakeholder review.

4. **Document all changes**: After validation, present a summary:
   - **Validated**: X requirements confirmed
   - **Updated**: Y requirements modified (list IDs)
   - **Removed**: Z requirements deleted (list IDs with reason)
   - **Escalated**: W contradictions added