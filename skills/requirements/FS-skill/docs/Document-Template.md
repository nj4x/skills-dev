# Requirements Document Template

Requirements documents MUST follow this structure.

---

## Template

```markdown
---
artifact-type: fs
lineage-rules: root
---

# [Category Name] Requirements

[Brief description of the requirements scope]

## Document Information
- **Category**: [Category-Version]
- **Version**: [Version number]
- **Source**: [Source documentation name]
- **Source Directory**: [Path to local source documents, e.g., `.data/FeatureSets_v2.0`]

### Source Documents

| Feature Set | Page ID | Local Path | Confluence URL |
|-------------|---------|------------|----------------|
| [Name] | [ID] | [Relative path to source folder] | [URL] |

### Contradictions (Conflicts / Inconsistencies) Found in Source Documents

| ID | Description | Source | Impact | Recommendation |
|----|-------------|--------|--------|----------------|
| ... | ... | ... | ... | ... |

---

## 1. [Grouping Name] ([ACRONYM])

### 1.1 [Sub-grouping if needed]

| ID | Requirement | Source |
|----|-------------|--------|
| ... | ... | ... |

---

## Appendix A: EARS Patterns Used

| Pattern | Template | Usage |
|---------|----------|-------|
| Ubiquitous | The [system] shall [action] | Basic functionality that always applies |
| Event-driven | When [trigger], the [system] shall [action] | Responses to specific events or actions |
| State-driven | While [state], the [system] shall [action] | Behavior during specific conditions |
| Unwanted behavior | If [condition], then the [system] shall [action] | Error handling and validation |
| Optional feature | Where [feature], the [system] shall [action] | Feature-specific behavior |
| Complex | Combinations of above patterns | Multi-condition requirements |

---

## Appendix B: Feature Set IDs

| Feature Set ID | Description | Source Page |
|----------------|-------------|-------------|
| ... | ... | ... |

---

## Appendix C: Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| [Version] | [YYYY-MM-DD] | [Author] | [Summary of changes] |
```

---

## Required Sections

1. **Header**: Title, description, document information
2. **Source Documents**: Table of referenced documents with URLs
3. **Contradictions**: Documented contradictions, conflicts, inconsistencies, and conflicting requirements (even if empty, include section)
4. **Requirements Sections**: Grouped by topic using numbered sections
5. **Appendix A - EARS Patterns**: Reference table for patterns used
6. **Appendix B - Feature Set IDs**: Mapping of feature set identifiers to sources
7. **Appendix C - Document History**: Version tracking with date, author, and change summary

---

## Output Location

Write requirements to an MD file under the requirements directory:
- Path: `<Project Root Dir>/requirements`
- Each category of requirements should have its own separate file (e.g., `<Requirement Category>.md`)
- Append new requirements to existing file, or create a new one if it doesn't already exist
- If requirements in existing file are outdated, modify them with newer statements instead of keeping both versions