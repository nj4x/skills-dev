# Backend Filtering Guide

This document provides rules and criteria for filtering Feature Set (FS) requirements into capability-level SRS contracts. Consult [Requirements boundary](../../../engineering/setup-lineage/SKILL.md#requirements-boundary): exclude invocation and realization mechanisms.

## Overview

Not all FS requirements are relevant to back-end implementation. This guide helps identify which requirements should be:
- **Included** in SRS (back-end relevant)
- **Excluded** from SRS (front-end only)
- **Partially included** (hybrid requirements)

> **Important - Category-Level Filtering**: When evaluating FS requirements, consider the relevance of entire FS categories to backend functionality. If an FS category primarily addresses UX/FE concerns (e.g., UI display, user interactions, visual presentation), the entire category may be excluded from SRS transformation. Only include FS categories that contain backend-relevant requirements such as data persistence, business logic, authorization, or API operations. **Exception**: Even if a category appears to be UX/FE focused, include requirements where user interaction scenarios imply backend support (i.e., require API calls for data retrieval, validation, or state changes).

---

## Include Criteria (Back-End Relevant)

Requirements are back-end relevant if they involve any of the following:

### 1. Data Persistence

Operations that create, store, or manage persistent data:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall create [entity]" | "create a new system role" | Data storage |
| "The system shall store [data]" | "store group information" | Data storage |
| "The system shall delete [entity]" | "delete the role" | Data removal |
| "The system shall maintain [state]" | "maintain audit log" | Data persistence |

### 2. Business Logic

Operations that implement business rules:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall validate [rule]" | "validate uniqueness" | Server-side validation |
| "The system shall calculate [value]" | "calculate member count" | Business computation |
| "The system shall enforce [constraint]" | "enforce nesting limit" | Rule enforcement |
| "The system shall ensure [condition]" | "ensure ID uniqueness" | Constraint checking |

### 3. Authorization & Access Control

Operations that check permissions:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall allow [role] to [action]" | "allow Super Admin to create" | Authorization |
| "The system shall prevent [role] from [action]" | "prevent Member from deleting" | Access control |
| "The system shall check [permission]" | "check if user has permission" | Permission verification |
| "The system shall verify [access]" | "verify organization scope" | Scope validation |

### 4. External Integrations

Operations that communicate with other systems:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall obtain [fact]" | "determine whether a role remains assigned" | Required external information |
| "The system shall notify [stakeholder]" | "make role creation observable" | Required observable effect |
| "The system shall react to [change]" | "revoke access after a user is removed" | Required lifecycle behavior |
| "The system shall keep [data] consistent" | "keep directory membership current" | Required consistency contract |

### 5. Data Retrieval

Operations that query and return data:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall return [data]" | "return RoleId and Version" | Query response |
| "The system shall list [entities]" | "list all system roles" | Data listing |
| "The system shall search [criteria]" | "search by RoleName" | Search operation |
| "The system shall filter [data]" | "filter by privilege" | Data filtering |

### 6. State Management

Operations that handle state transitions:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall track [state]" | "track version number" | State tracking |
| "The system shall increment [counter]" | "increment version" | Counter management |
| "The system shall transition [state]" | "transition to active" | State machine |

### 7. Constraint Enforcement

Operations that enforce data integrity:

| Pattern | Example | Why Back-End |
|---------|---------|--------------|
| "The system shall limit [constraint]" | "limit nesting to 2 levels" | Constraint enforcement |
| "The system shall restrict [operation]" | "restrict circular references" | Operation restriction |
| "The system shall require [field]" | "require Group Name" | Required field validation |

---

## Exclude Criteria (Front-End Only)

Requirements are front-end only if they EXCLUSIVELY involve:

### 1. Pure UI Display

Visual presentation without data logic:

| Pattern | Example | Why Front-End |
|---------|---------|---------------|
| "Display [X] at top of list" | "Display Teacher Group at top" | Visual ordering |
| "Show [element]" | "Show button" | Element visibility |
| "Highlight [element]" | "Highlight selected row" | Visual feedback |
| "Position [element]" | "Position modal center" | Layout |

### 2. UI Interaction

User interface interactions without server calls:

| Pattern | Example | Why Front-End |
|---------|---------|---------------|
| "When [button] clicked" (UI only) | "When tab clicked, switch view" | Client-side interaction |
| "When [element] clicked, display [info]" | "When Admin Authority number is clicked, the system shall display all assigned authority details." | UI display trigger |
| "On hover, [action]" | "On hover, show tooltip" | Visual feedback |
| "Expand/collapse [element]" | "Expand section" | UI state |
| "Toggle [element]" | "Toggle checkbox" | Client-side toggle |

### 3. UI Layout & Styling

Presentation and styling requirements:

| Pattern | Example | Why Front-End |
|---------|---------|---------------|
| "Arrange in [layout]" | "Arrange in grid" | Layout |
| "Style with [format]" | "Bold text" | Styling |
| "Color [element]" | "Color row red" | Visual styling |
| "Font [specification]" | "14px font size" | Typography |

### 4. Client-Side Validation

Validation that can be done without server:

| Pattern | Example | Why Front-End |
|---------|---------|---------------|
| "Show error message" | "Show 'field required' message" | UI feedback |
| "Highlight invalid field" | "Red border on empty field" | Visual validation |
| "Instant feedback" | "Show character count" | Real-time UI |

### 5. Navigation

Page/route navigation:

| Pattern | Example | Why Front-End |
|---------|---------|---------------|
| "Navigate to [page]" | "Navigate to settings" | Routing |
| "Open [modal/dialog]" | "Open confirmation dialog" | Modal display |
| "Redirect to [page]" | "Redirect to login" | Client routing |

---

## Hybrid Requirements (Partial Inclusion)

Some requirements have both front-end and back-end aspects:

### Pattern: UI Trigger + Server Action

**FS Example:**
```
"When Delete button clicked, the system shall remove the member from Teacher Group"
```

**Analysis:**
- Front-end: "When Delete button clicked" → UI event handling
- Back-end: "system shall remove the member" → Data operation

**SRS Extraction:**
```
"The system shall remove the member from Teacher Group"
(UI trigger noted but not primary focus)
```

### Pattern: Display + Data Retrieval

**FS Example:**
```
"The system shall display the allocated Admin Role for each group"
```

**Analysis:**
- Front-end: "display" → UI rendering
- Back-end: "allocated Admin Role for each group" → Data retrieval

**SRS Extraction:**
```
"The system shall return the allocated Admin Role for each group"
(Focus on data retrieval, not display mechanism)
```

### Pattern: User Input + Server Processing

**FS Example:**
```
"The system shall allow partial search by name and ID when adding members"
```

**Analysis:**
- Front-end: Input field, autocomplete UI
- Back-end: Search query, matching logic

**SRS Extraction:**
```
"The system shall support partial match search by name and ID for members"
(Focus on search capability, not input mechanism)
```

---

## Filtering Decision Matrix

| Requirement Pattern | Decision | Reason |
|--------------------|----------|--------|
| "create/store/delete [entity]" | **Include** | Data persistence |
| "validate/ensure/enforce [rule]" | **Include** | Business logic |
| "allow/prevent [role] to [action]" | **Include** | Authorization |
| "call/publish/consume [external]" | **Include** | Integration |
| "return/list/search [data]" | **Include** | Data retrieval |
| "display at [position]" | **Exclude** | Pure UI |
| "when [button] clicked" only | **Exclude** | UI interaction |
| "highlight/color/style [element]" | **Exclude** | UI styling |
| "navigate to [page]" | **Exclude** | Client routing |
| "when [trigger], system shall [action]" | **Partial** | Extract server action |

---

## Filtering Process

### Step 1: Categorize Each FS Requirement

For each FS requirement, determine its category:

```markdown
| FS ID | Category | Include? | Reason |
|-------|----------|----------|--------|
| GRP-FS-STRUC-001 | Data persistence | Yes | Stores nested structure |
| GRP-FS-TCHR-016 | Pure UI display | No | Display ordering only |
| GRP-FS-TCHR-015 | Hybrid | Partial | Delete operation + UI trigger |
```

### Step 2: Extract Back-End Portions from Hybrid

For hybrid requirements:
1. Identify the server-side action
2. Reframe requirement focusing on system behavior
3. Note original FS ID for traceability

### Step 3: Create Filtered Requirements List

Final output:

```markdown
## Included Requirements (Back-End Relevant)

| FS ID | Original Requirement | Extracted for SRS |
|-------|---------------------|-------------------|
| GRP-FS-STRUC-001 | "support nested group structures" | Include as-is |
| GRP-FS-TCHR-015 | "When member selected and Delete clicked, remove member" | "remove member from Teacher Group" |

## Excluded Requirements (Front-End Only)

| FS ID | Requirement | Reason for Exclusion |
|-------|-------------|---------------------|
| GRP-FS-TCHR-016 | "display Teacher Group at top" | Pure UI ordering |
| GRP-FS-TCHR-006 | "prevent selection for bulk operations" | UI interaction only |
```

---

## Special Cases

### Case 1: Sorting/Ordering

| Scenario | Include? | Reason |
|----------|----------|--------|
| "Allow sorting by [field]" | Yes | Server-side sort capability |
| "Display sorted by [field]" | Partial | Extract sort capability |
| "Show at top of list" | No | UI display order |

### Case 2: Validation

| Scenario | Include? | Reason |
|----------|----------|--------|
| "Validate field is unique" | Yes | Server-side validation |
| "Ensure max 200 characters" | Yes | Constraint enforcement |
| "Show error if empty" | No | Client-side feedback |
| "Highlight invalid fields" | No | UI feedback |

### Case 3: User Feedback

| Scenario | Include? | Reason |
|----------|----------|--------|
| "Return error code X" | Yes | API response |
| "Display error message" | No | UI display |
| "Log failed attempt" | Yes | Server-side logging |
| "Show success notification" | No | UI notification |

### Case 4: Permissions

| Scenario | Include? | Reason |
|----------|----------|--------|
| "Allow [role] to [action]" | Yes | Authorization |
| "Hide [button] for [role]" | No | UI visibility |
| "Disable [action] for [role]" | Partial | Check permission + UI state |

---

## Filtering Checklist

When reviewing each FS requirement, ask:

- [ ] Does this requirement involve data creation, modification, or deletion?
- [ ] Does this requirement implement business rules or constraints?
- [ ] Does this requirement involve authorization or permission checks?
- [ ] Does this requirement communicate with external systems?
- [ ] Does this requirement return or query data?
- [ ] Is this requirement ONLY about visual display or UI interaction?
- [ ] If hybrid, what is the server-side portion to extract?

---

## Example: Groups FS Filtering

### Included (Back-End)

| FS ID | Requirement | Category |
|-------|-------------|----------|
| GRP-FS-STRUC-001 | Support nested group structures | Data structure |
| GRP-FS-STRUC-002 | Limit nesting to 2 levels | Constraint |
| GRP-FS-NAME-001 | Require Group Name | Validation |
| GRP-FS-NAME-013 | Ensure Group ID uniqueness | Constraint |
| GRP-FS-CRUD-001 | Allow Super Admin to create groups | Authorization |
| GRP-FS-MEMB-010 | Allow Owners to invite members | Authorization + Operation |

### Excluded (Front-End Only)

| FS ID | Requirement | Reason |
|-------|-------------|--------|
| GRP-FS-TCHR-016 | Display Teacher Group at top of list | UI ordering |
| GRP-FS-TCHR-006 | Prevent selection for bulk operations | UI interaction |
| GRP-FS-ROLE-013 | When Authority number clicked, display details | UI interaction |

### Partial (Hybrid)

| FS ID | Original | Extracted for SRS |
|-------|----------|-------------------|
| GRP-FS-TCHR-015 | When member selected and Delete clicked, remove member | Remove member from Teacher Group |
| GRP-FS-ROLE-011 | Display allocated Admin Role for each group | Return allocated Admin Role data for each group |