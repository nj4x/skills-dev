# Quality Check Guide

## Validation with Semantic Search

Use `search_documents` to validate each requirement against source documents.

For each generated requirement:
1. Craft a search query based on the requirement's key concepts
2. Execute semantic search against source documents
3. Verify the search results support the requirement
4. If no support found, flag for removal or modification

---

## Accuracy Verification

- Search source documents multiple times with different queries to ensure generated requirements are accurate
- Review user requirements input to confirm alignment
- Document any contradictions (conflicts, inconsistencies, conflicting requirements) found in source documents or user input

---

## Contradiction / Conflict Documentation Format

Include a "Contradictions Found in Source Documents" section with the following table structure:

| Column | Description |
|--------|-------------|
| ID | Unique identifier (CONTR-001, CONTR-002, etc.) |
| Description | Bold title followed by detailed explanation |
| Source | Document name with page ID reference |
| Impact | Current status (Resolved, Open, or severity assessment) |
| Recommendation | Resolution approach or action taken |

### Example Table

| ID | Description | Source | Impact | Recommendation |
|----|-------------|--------|--------|----------------|
| ~~CONTR-001~~ | ~~**Field Length Discrepancy**: Policy doc states 73 chars, Feature doc states 200 chars.~~ | ~~Policy (1590539350) vs Feature (1600150581)~~ | ~~Resolved~~ | ~~Resolved: v2.0 document supersedes older policy. Updated to 200 chars.~~ |
| CONTR-002 | **Permission Inconsistency**: Table shows X but description allows access. | Policy (1590539350) | Open | Clarification needed from stakeholders. |

### Formatting Rules

For resolved contradictions:
- Use ~~strikethrough~~ formatting for the entire row
- Add "Resolved:" prefix to the Recommendation with explanation