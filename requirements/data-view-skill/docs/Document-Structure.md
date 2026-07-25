# Data View Document Structure

This document defines the required sections and ordering for a Data View document.

---

## Required Section Ordering

```
1. Title and Document Information
2. References
3. Considerations (Design Decisions)
4. Access Patterns Summary
5. Table Definitions (with GSIs)
6. Query Patterns (by SRS section / API endpoint)
7. CUD Constraints
8. Points of Interest
```

---

## 1. Title and Document Information

```markdown
# Data View | [Service Domain]

## Document Information

| Field | Value |
|-------|-------|
| **Document ID** | [DOMAIN]-DV |
| **Category** | Data View |
| **Version** | [Version — always starts at 1.0] |
| **Status** | Draft / Final |
| **Created** | [Date] |
| **Related SRS** | [SRS Document ID and version] |
| **Related API** | [API Definition Document ID and version] |
| **Database** | Amazon DynamoDB |
| **Design Pattern** | Single Table / Multi-Table / Hybrid |
```

---

## 2. References

Include links to:
- Source SRS document (with Confluence URL)
- Source API Definition document (with Confluence URL)
- Source Use Case Diagrams document (with Confluence URL if available)

Do NOT include generic DynamoDB tutorial links. Only include references directly used in this design.

---

## 3. Considerations (Design Decisions)

Document key architectural decisions as a table with options evaluated and chosen approach:

```markdown
# Considerations

| Item | Options | Notes |
|------|---------|-------|
| [Decision] | Option A (Chosen) | [Rationale] |
|            | Option B | [Why not chosen] |
```

See [Considerations-Template.md](./Considerations-Template.md) for the required decisions.

---

## 4. Access Patterns Summary

A single reference table listing ALL access patterns before diving into details:

```markdown
# Access Patterns Summary

| # | Access Pattern | API / Event | Table / GSI | Operation |
|---|---------------|-------------|-------------|-----------|
| 1 | Get group by UUID | GRP-API-102 | GroupById → Group | GetItem + GetItem |
| 2 | List groups for org | GRP-API-103 | Group | Query |
```

This provides a quick overview before the detailed query patterns section.

---

## 5. Table Definitions

For each table, document in this order:

```markdown
## [Table Name] Table

[One-line purpose description]

### Schema

| PK (S) | SK (S) | attr1 (type) | attr2 (type) | ... |
|--------|--------|-------------|-------------|-----|
| [key pattern] | [key pattern] | [description] | [description] | |

### Field Descriptions

* **PK**: [what the partition key represents]
* **SK**: [what the sort key represents]
* **attr1**: [description, constraints, enum values]

### GSIs

| GSI Name | PK | SK | Projection | Purpose |
|----------|----|----|------------|---------|
| [name] | [attr] | [attr] | ALL / KEYS_ONLY | [query pattern it supports] |
```

Follow [Table-Design.md](./Table-Design.md) for conventions.

---

## 6. Query Patterns (by SRS section)

Group query patterns by SRS functional requirement section. For each section:

```markdown
## [SRS-SECTION-ID]: [Section Name]

### [Operation Name]

`[HTTP Method] [Path]` → [API-ID]

| Use Case | Steps | Query Patterns | Notes |
|----------|-------|----------------|-------|
| [use case] | [step] | [DDB operation] | [notes] |
```

Follow [Query-Pattern-Notation.md](./Query-Pattern-Notation.md) for notation conventions.

---

## 7. CUD Constraints

```markdown
# CUD Constraints

| Use Case | Constraints | DynamoDB Implementation |
|----------|-------------|----------------------|
| [Operation] | * constraint | [How enforced: condition, transaction, app-side] |
```

Follow [CUD-Constraints.md](./CUD-Constraints.md) for patterns.

---

## 8. Points of Interest

Document open questions, risks, and design considerations:

```markdown
# Points of Interest

1. **[Topic]**
   1. [Context and concern]
   2. [Options or recommendations]
```

Keep to genuine open questions and risks. Do NOT document obvious DynamoDB basics.

---

## Table Summary (Optional, at end)

If multiple tables, include a summary:

```markdown
# Table Summary

| # | Table | PK | SK | GSIs | Purpose |
|---|-------|----|----|------|---------|
| 1 | [name] | [pk] | [sk] | [count] | [one-line] |
```

---

## Sections Intentionally Excluded

The following sections from some reference Data Views were evaluated and excluded for conciseness:

| Excluded Section | Reason |
|-----------------|--------|
| **Legend** | Color-coding doesn't render in markdown; use text annotations instead |
| **Data Flow Diagrams** | Already covered in Use Case Diagrams companion document |
| **Entity Relationship Diagrams** | Already covered in SRS Entity Reference |
| **Affected External Module Tables** | Document only if this service writes to external tables; omit if read-only dependencies |
| **Archive / Expired schemas** | Historical versions should be in version control, not the active document |

---

## Full Output Template

Use this as a copy-paste skeleton when generating a Data View document:

````markdown
# Data View | [Service Domain]

## Document Information

| Field | Value |
|-------|-------|
| **Document ID** | [DOMAIN]-DV-[VERSION] |
| **Category** | Data View |
| **Version** | [Version] |
| **Status** | Draft |
| **Created** | [Date] |
| **Related SRS** | [SRS Document ID (version)] |
| **Related API** | [API Definition Document ID (version)] |
| **Database** | Amazon DynamoDB |
| **Design Pattern** | [Single Table / Multi-Table / Hybrid] |

---

# References

* [SRS Document Title](confluence-url)
* [API Definition Document Title](confluence-url)
* [Use Case Diagrams Document Title](confluence-url)

---

# Considerations

| Item | Options | Notes |
|------|---------|-------|
| [Decision 1] | **Option A** (Recommended) | [Rationale] |
|               | Option B | [Why not chosen] |

---

# Access Patterns Summary

| # | Access Pattern | API / Event | Table / GSI | Operation |
|---|---------------|-------------|-------------|-----------|
| 1 | [Pattern name] | [API-ID] | [Table] | [DDB operation type] |

---

# [Table Name] Table

[Purpose]

### Schema

| PK (S) | SK (S) | attr1 (type) | attr2 (type) |
|--------|--------|-------------|-------------|
| [pattern] | [pattern] | [description] | [description] |

### Field Descriptions

* **PK**: [description]
* **SK**: [description]

### GSIs

| GSI Name | PK | SK | Projection | Purpose |
|----------|----|----|------------|---------|
| [name] | [attr] | [attr] | [type] | [purpose] |

---

# Query Patterns

## [SRS-SECTION-ID]: [Section Name]

### [Operation Name]

`[HTTP Method] [Path]` → [API-ID]

| Use Case | Steps | Query Patterns | Notes |
|----------|-------|----------------|-------|
| [use case] | [step] | [DDB operation] | [notes] |

---

# CUD Constraints

| Use Case | Constraints | DynamoDB Implementation |
|----------|-------------|----------------------|
| [Operation] | * [constraint] | [How enforced] |

---

# Table Summary

| # | Table | PK | SK | GSIs | Purpose |
|---|-------|----|----|------|---------|
| 1 | [name] | [pk] | [sk] | [count] | [purpose] |

---

# Points of Interest

1. **[Topic]**
   1. [Context]
   2. [Recommendation]
````

---

## Required Sections Checklist

Every Data View document MUST include all of these sections:

- [ ] Document Information header with all required fields
- [ ] References (SRS, API Definition, Use Cases links)
- [ ] Considerations table with all design decisions evaluated
- [ ] Access Patterns Summary table
- [ ] At least one Table Definition with Schema, Field Descriptions
- [ ] GSI documentation for tables that have GSIs
- [ ] Query Patterns for every API endpoint
- [ ] Query Patterns for every consumed event handler
- [ ] CUD Constraints table
- [ ] Table Summary (if multiple tables)
- [ ] Points of Interest (at least one open question or risk)
