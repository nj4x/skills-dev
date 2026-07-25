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

## Module View Diagram (Optional)

> **⚠️ OPTIONAL**: This section is only included if the user confirmed module view generation at **Checkpoint #2.5** in the SRS-skill workflow. Omit this entire section if the user declined.

This section provides a high-level architectural view of the system modules and their relationships.

### System Architecture

![Module View Diagram](./diagrams/[DOMAIN]-module-view.drawio.svg)

*Figure 1: Module view diagram showing system components and their interactions*

### Module Descriptions

| Module | Responsibility | Dependencies |
|--------|----------------|--------------|
| [Module Name] | [Brief description of module responsibility] | [List of dependent modules] |

### Notes

- The diagram should be created using draw.io and exported as SVG
- Store the source file (`.drawio`) alongside the SVG for future edits
- Update the diagram when adding new modules or changing relationships

---

## Dependencies

This section lists external systems and services that this module depends on. Dependencies were identified during requirements analysis and approved by stakeholders.

| # | System/Service | Type | Description | User Notes |
|---|----------------|------|-------------|------------|
| 1 | [Service Name] | API | [What API is called and why] | [Stakeholder notes/clarifications] |
| 2 | [Service Name] | Event | [What event is consumed and why] | [Stakeholder notes/clarifications] |

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

## API Reference

> **Note**: This section provides a summary of available APIs. For detailed specifications including request/response schemas, status codes, and examples, see the companion document: **[DOMAIN]-API-Definition-[VERSION].md**

### Internal APIs

| Operation | Method | Path | Description |
|-----------|--------|------|-------------|
| [OpName] | [HTTP] | /internal/[path] | [Brief description] |

### Administrative APIs

| Operation | Method | Path | Description |
|-----------|--------|------|-------------|
| [OpName] | [HTTP] | /v2/[path] | [Brief description] |

### Related Documents

- **API Definition Document**: [DOMAIN]-API-Definition-[VERSION].md - Full API specifications with request/response schemas, status codes, error handling, and examples

---

## Main Use Cases

This section outlines the primary use cases implemented by this system. Detailed sequence diagrams for each use case are provided in the companion document.

### Use Case Summary

| UC ID | Use Case Name | Primary Actor | Description |
|-------|---------------|---------------|-------------|
| UC-001 | [Use Case Name] | [Actor] | [Brief description of the use case] |
| UC-002 | [Use Case Name] | [Actor] | [Brief description of the use case] |

### Use Case Descriptions

#### UC-001: [Use Case Name]

- **Actor**: [Primary actor]
- **Preconditions**: [What must be true before execution]
- **Main Success Scenario**: [Brief summary of happy path]
- **Alternative Scenarios**: [Brief summary of alternatives]
- **Postconditions**: [What is true after successful execution]

### Related Documents

- **Use Case Diagrams Document**: [DOMAIN]-Use-Case-Diagrams-[VERSION].md - Sequence diagrams for each use case with detailed actor interactions and message flows

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

**Inputs:**
- [Input field 1]: [Description]
- [Input field 2]: [Description]

**Outputs:**
- [Output field 1]: [Description]
- [Output field 2]: [Description]

**Test Cases:** *(Optional — only if confirmed at Checkpoint #2.5)*

1. [SRS-ID]-P-001
   - Given [precondition]
   - [HTTP Method] `[Endpoint]` API call must return a `[Status]` status with [expected response]

2. [SRS-ID]-N-001
   - Given [failure condition]
   - [HTTP Method] `[Endpoint]` API call must return a `[Error Status]` status with an `error.code: [ERROR_CODE]`

**Source FS Requirements:**
- [FS-ID-001]: [Brief FS requirement description]
- [FS-ID-002]: [Brief FS requirement description]

---

## Appendix A: FS-to-SRS Traceability Matrix

| SRS Requirement ID | Source FS ID(s) | Description |
|--------------------|-----------------|-------------|
| [SRS-X.0.0] | [FS-001, FS-002] | [Brief description] |

---

## Appendix B: Test Case Summary (Optional)

> **⚠️ OPTIONAL**: This appendix is only included if the user confirmed test case generation at **Checkpoint #2.5**. Omit if test cases were declined.

| SRS ID | Total | P (Positive) | N (Negative) | E (Edge) | S (Security) |
|--------|-------|--------------|--------------|----------|--------------|
| [X.0.0] | [N] | [N] | [N] | [N] | [N] |
| **Total** | [Sum] | [Sum] | [Sum] | [Sum] | [Sum] |


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
    <p><strong>Test Cases:</strong></p>
    <ol>
      <li>[Test case 1]</li>
      <li>[Test case 2]</li>
    </ol>
  </panel>
</panel>
```

---

## Required Sections Checklist

Every SRS document MUST include:

- [ ] Document Information header
- [ ] Source Feature Sets table
- [ ] Dependencies section (with user-approved dependencies and notes)
- [ ] Entity Reference (if entities exist)
- [ ] Event Reference (if events exist)
- [ ] API Reference (summary)
- [ ] Main Use Cases
- [ ] At least one Feature Set section (X.0)
- [ ] At least one Requirement subsection (X.0.Y)
- [ ] Source FS attribution for each requirement
- [ ] Appendix A: Traceability Matrix
- [ ] Document History

### Optional Sections (Include if confirmed at Checkpoint #2.5)

- [ ] Module View Diagram — only if `generate_module_view = true`
- [ ] Test Cases for each requirement — only if `generate_test_cases = true`
- [ ] Appendix B: Test Case Summary — only if `generate_test_cases = true`

### Excluded Sections (NOT part of standard SRS)

The following appendices are **NOT generated** by the SRS skill and must **NOT be added** to SRS documents:

- ❌ **Appendix C: Error Code Reference** — Error codes belong in the API Definition companion document (`[DOMAIN]-API-Definition-[VERSION].md`), not in the SRS. Do NOT add an Appendix C to SRS documents.

### Companion Documents

Every SRS should be accompanied by:

- [ ] API Definition Document ([DOMAIN]-API-Definition-[VERSION].md)
- [ ] Use Case Diagrams Document ([DOMAIN]-Use-Case-Diagrams-[VERSION].md)

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
