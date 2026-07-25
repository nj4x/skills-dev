# Requirement Format Guide

## Table Format

Requirements MUST be formatted in tables with the following columns:

| Column | Description |
|--------|-------------|
| ID | Requirement ID following the naming convention |
| Requirement | EARS-formatted requirement statement |
| Source | Hyperlink to source document(s) |

### Example Table

| ID | Requirement | Source |
|----|-------------|--------|
| GRP-FS-MEMB-001 | The system shall support three membership roles for groups: Owner, Manager, and Member. | [Group Policy](https://confluence.example.com/pages/viewpage.action?pageId=1590539350) |
| GRP-FS-MEMB-002 | When a user with Owner role performs an action on the group, the system shall grant full management capabilities including group deletion. | [Group Policy](https://confluence.example.com/pages/viewpage.action?pageId=1590539350) |

---

## ID Encoding

```
[Category Acronym]-[Type]-[Grouping]-[Number]

Example: OU-FS-DOMAIN-1
```

| Component | Description | Example |
|-----------|-------------|---------|
| Category Acronym | 3-5 uppercase letters | GRP, OU, ROLE |
| Type | FS or SRS | FS |
| Grouping | Related topic | DOMAIN, MEMB |
| Number | Sequential identifier | 001, 002 |

---

## ID Stability Rules

> **⚠️ CRITICAL**: Requirement IDs may be referenced in other documents (SRS, test cases, traceability matrices). ID stability is essential for document integrity.

### Rules

1. **DO NOT renumber requirement IDs** after they are assigned
2. **When a requirement is removed**: Leave the ID gap - do not shift subsequent IDs
3. **When adding new requirements**: Use the next available number in sequence (or fill gaps if explicitly requested by user)

### Example - Correct Handling of Removed Requirements

**Before removal:**
```
| GRP-FS-STRUC-001 | The system shall support nested groups. |
| GRP-FS-STRUC-002 | The system shall limit nesting to 2 levels. |  ← To be removed
| GRP-FS-STRUC-003 | The system shall prevent circular references. |
```

**After removal (CORRECT - gap preserved):**
```
| GRP-FS-STRUC-001 | The system shall support nested groups. |
| GRP-FS-STRUC-003 | The system shall prevent circular references. |
```

**After removal (WRONG - IDs renumbered):**
```
| GRP-FS-STRUC-001 | The system shall support nested groups. |
| GRP-FS-STRUC-002 | The system shall prevent circular references. |  ← WRONG: was STRUC-003
```

### Rationale

- Requirement IDs serve as stable references across multiple documents
- SRS documents may reference FS requirement IDs for traceability
- Test cases may be linked to specific requirement IDs
- Renumbering breaks these cross-references and causes confusion

---

## Source Reference Format

### Confluence Links
- Use Markdown hyperlinks: `[Document Name](URL)`
- When multiple sources apply, list them comma-separated: `[Doc1](URL1), [Doc2](URL2)`

### MCP Tool for Link Generation
**Use MCP tool `generate_wiki_link`** to generate Confluence URLs from downloaded wiki directories:
- Call `generate_wiki_link(path="./path/to/wiki_page_directory")` 
- The tool returns both `url` (plain link) and `markdown` (formatted `[Title](URL)`)
- Example: `generate_wiki_link(path=".data/FeatureSets_v2.0/Group_Policy_1590539350")`

---

## Local Path Tracking

When working with downloaded source documents, include local file paths for traceability:

| Element | Description | Example |
|---------|-------------|---------|
| **Source Directory** | Add root directory to Document Information | `.data/FeatureSets_v2.0` |
| **Local Paths** | Paths relative to project root in Source Documents table | `.data/FeatureSets_v2.0/.Group__Policy_v2.0_1590539350/` |
| **Path Format** | Use relative paths | `.data/FeatureSets_v2.0/...` |
| **Derivation** | Extract folder names from downloaded wiki page directories | Format: `.{Title}_v{Version}_{PageID}/` |