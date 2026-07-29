# SRS Document Structure

This document defines the standard structure for Software Requirements Specification (SRS) documents generated from Feature Set (FS) requirements.

## Document Template

```markdown
# [Domain Name] | Software Requirements Specification

## Document Information

| Field | Value |
|-------|-------|
| **Document ID** | [DOMAIN]-SRS-[VERSION] |
| **Category** | SRS (Software Requirements Specification) |
| **Version** | [Major.Minor] |
| **Status** | [Draft/Review/Final] |
| **Created** | [Date] |
| **Source FS** | [FS Document ID] |

---

## Source Feature Sets

| Feature Set | Document ID | Version | Source URL |
|-------------|-------------|---------|------------|
| [FS Name] | [FS-ID] | [Version] | [Confluence URL] |

---

## Entity Reference

| Entity | Description |
|--------|-------------|
| [EntityName] | [Brief description of the entity] |

### [EntityName] Attributes

| Attribute | Type | Required | Immutable | Description |
|-----------|------|----------|-----------|-------------|
| [attr1] | [type] | Yes/No | Yes/No | [description] |

---

## Event Reference

### Events Produced

| Event Name | Trigger | Attributes | Description |
|------------|---------|------------|-------------|
| [EventName] | [When triggered] | [Key attributes] | [What it signals] |

### Events Consumed

| Event Name | Source | Handler | Description |
|------------|--------|---------|-------------|
| [EventName] | [Origin system] | [How processed] | [Expected behavior] |

---

## [Section X.0] [Feature Set Name]

[Brief description of this feature set's purpose and scope]

### Feature Set Metadata

| Field | Value |
|-------|-------|
| **Actor** | [Primary actor(s)] ([CRUD permissions]) |
| **Permissions** | [Required permissions or N/A] |
| **Stakeholders** | [List of stakeholders] |
| **Since** | [Version introduced] |

### Characteristics

- [Key characteristic 1]
- [Key characteristic 2]
- [Additional characteristics]

---

### [Section X.0.Y] [Requirement Name]

[Description of this requirement group]

**Requirements:**

- The system shall [requirement statement 1]
- The system shall [requirement statement 2]
- [Additional requirement statements]

**Lifecycle and Safety Conditions:**
- [Precondition, postcondition, invariant, or failure behavior]

**Source FS Requirements:**
- [FS-ID-001]: [Brief FS requirement description]
- [FS-ID-002]: [Brief FS requirement description]

---

## Appendix A: FS-to-SRS Traceability Matrix

| SRS Requirement ID | Source FS ID(s) | Description |
|--------------------|-----------------|-------------|
| [SRS-X.0.0] | [FS-001, FS-002] | [Brief description] |

---

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| [X.Y] | [Date] | [Author] | [Change description] |
```

---

## Section Numbering Convention

### Major Sections (X.0)
Major feature sets or functional areas:
- 1.0 - First major feature set
- 2.0 - Second major feature set
- etc.

### Subsections (X.0.Y)
Individual operations or requirement groups within a feature set:
- X.0.0 - Create operation
- X.0.1 - Update operation
- X.0.2 - Delete operation
- X.0.3 - View operation (single)
- X.0.4 - List operation (multiple)

### Common Ordering
```
X.0.0 - Create [Resource]
X.0.1 - Update [Resource]
X.0.2 - Delete [Resource]
X.0.3 - View [Resource]
X.0.4 - List [Resources]
X.0.5 - Search [Resources]
```

---

## Panel Structure (HTML Output)

When generating HTML output (like Confluence), use nested panel structure:

```html
<panel>
  <h2>[X.0] Feature Set Name</h2>
  <p>[Feature set description]</p>
  
  <panel>
    <!-- Metadata panel -->
    <p><strong>Actor</strong>: [Actor info]</p>
    <p><strong>Permissions</strong>: [Permission info]</p>
    <p><strong>Stakeholders</strong>: [List]</p>
    <p><strong>Since</strong>: [Version]</p>
  </panel>
  
  <panel>
    <!-- Characteristics panel -->
    <h3>Characteristics</h3>
    <ul>
      <li>[Characteristic 1]</li>
      <li>[Characteristic 2]</li>
    </ul>
  </panel>
  
  <panel>
    <!-- Individual requirement panel -->
    <h3>[X.0.0] Requirement Name</h3>
    <ul>
      <li>[Requirement bullet]</li>
    </ul>
    <p><strong>Lifecycle and Safety Conditions:</strong> [Precondition, postcondition, invariant, or failure behavior]</p>
  </panel>
</panel>
```

---

## Required Sections Checklist

Every SRS document MUST include:

- [ ] Document Information header
- [ ] Source Feature Sets table
- [ ] Entity Reference (if entities exist)
- [ ] Event Reference (if event semantics are required)
- [ ] At least one Feature Set section (X.0)
- [ ] At least one Requirement subsection (X.0.Y)
- [ ] Lifecycle and safety conditions where relevant
- [ ] Source FS attribution for each requirement
- [ ] Appendix A: Traceability Matrix
- [ ] Document History

### Excluded Sections

Do not add API contracts, sequence diagrams, data-realization details, module views, test cases, or companion-document links. Those mechanisms belong in the ADR that selects or changes them; consult [Requirements boundary](../../../engineering/setup-lineage/SKILL.md#requirements-boundary).

---

## Metadata Field Definitions

### Actor
The user or system that performs the operation:
- Format: `[Actor Name] ([CRUD permissions])`
- Example: `SAB Role Management Owner (CRUD); SAB Client Organizations (R)`

### Permissions
Required permissions to perform operations:
- Use `N/A` if no specific permissions required
- List specific permission names if applicable

### Stakeholders
Systems or teams affected by or interested in the requirements:
- Use bullet points for multiple stakeholders
- Include both internal and external stakeholders

### Since
Version when the feature was introduced:
- Format: `Version X.Y`
- **MUST use the version from the Document ID** (e.g., `2.0` from `GRP-SRS-2.0`), NOT the frequently-updated `Version` field in the Document Information table (e.g., `2.29`). The Document ID version represents the feature release version.
- Use status badge for visual emphasis in HTML
