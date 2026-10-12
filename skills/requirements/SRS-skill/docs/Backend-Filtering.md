# FS-to-SRS Transformation Guide

This document defines how to turn Feature Set (FS) requirements into capability-level SRS contracts. Consult [Requirements boundary](../../../engineering/setup-lineage/SKILL.md#requirements-boundary) and its [Granularity](../../../engineering/setup-lineage/SKILL.md#granularity) subsection first.

## Overview

The transformation has three steps:

1. **Filter** — keep FS items that imply a system guarantee; drop items that are only UI presentation.
2. **Extract** — for hybrid items, keep the system guarantee and drop the UI trigger or display.
3. **Refine** — add the precision the FS leaves implicit: conditions, failure behavior, authorization per actor, and measurable targets.

An SRS item that only restates its FS item is incomplete. An SRS item that names an endpoint, error code, payload field, transport, topic, storage, or library has crossed into an ADR.

> **Category-level filtering**: If an FS category addresses only UI presentation (display, layout, navigation), exclude the whole category. **Exception**: include any item where a user interaction implies a system guarantee — data retrieval, validation, authorization, or a state change.

---

## Step 1: Filter

### Include — the item implies a system guarantee

| Kind | FS pattern | Example |
|------|------------|---------|
| Lifecycle | create, change, remove, retain an entity | "create a system role" |
| Business rule | validate, enforce, ensure, limit, require | "limit nesting to 2 levels" |
| Authorization | allow or prevent a role to act | "allow Super Admin to create groups" |
| Retrieval | find, list, search, filter, sort data | "search members by name" |
| State | track or transition state | "deactivate a group" |
| External dependency | obtain a fact from, or keep consistent with, another system | "revoke access after a user leaves the directory" |
| Observable effect | make a change known to a stakeholder | "make role creation observable to audit" |
| Quality | user-perceived quality expectation | "show search results without noticeable delay" |

### Exclude — the item is only UI presentation

| Kind | FS pattern | Example |
|------|------------|---------|
| Display | display, show, highlight, position | "Display Teacher Group at top of list" |
| Interaction | click, hover, expand, toggle with no state change | "When tab clicked, switch view" |
| Styling | layout, color, font | "Color row red" |
| Client feedback | show message, highlight field, character counter | "Show 'field required' message" |
| Navigation | navigate, open dialog, redirect | "Open confirmation dialog" |

### Partial — hybrid items

| FS pattern | Decision |
|------------|----------|
| "When [UI trigger], the system shall [change]" | Keep the change, drop the trigger |
| "The system shall display [data]" | Keep "make [data] available to [actor]", drop the display |
| "Allow [input] when [UI context]" | Keep the capability, drop the input mechanism |
| "Disable/hide [action] for [role]" | Keep "prevent [role] from [action]", drop the UI state |

---

## Step 2: Extract

For each hybrid item:

1. Identify the system guarantee.
2. Restate it as system behavior toward an actor, with no UI words and no mechanism.
3. Keep the original FS ID for traceability.

| FS ID | FS item | Extracted guarantee |
|-------|---------|---------------------|
| GRP-FS-TCHR-015 | When member selected and Delete clicked, remove member | The system shall remove a member from a Teacher Group |
| GRP-FS-ROLE-011 | Display allocated Admin Role for each group | The system shall make the allocated Admin Role of each group available to authorized actors |
| GRP-FS-MEMB-020 | Allow partial search by name and ID when adding members | The system shall find members by partial name or partial ID |

---

## Step 3: Refine

For every included or extracted item, answer each question below. Add an SRS statement for each answer that applies. Record "none" when a question does not apply.

| Question | Adds |
|----------|------|
| What must be true before the action? | Preconditions |
| What is true after success? | Postconditions |
| What must always stay true? | Invariants |
| What happens on invalid input, denied access, missing entity, or conflicting change? | Failure behavior (stated as outcome, not error code) |
| Which actors may do it, and in which scope? | Authorization per actor |
| Which entity attributes does it read or change? | Entity Reference entries, in business terms |
| Must other parties learn of the change? | Produced or consumed events, by meaning |
| Is there a quality expectation? | NFR with metric, threshold, unit, condition |

### Example

**FS item** — GRP-FS-STRUC-002: "The system shall limit group nesting to 2 levels."

**SRS item:**

```markdown
### GRP-FR-1.0.3 Limit Group Nesting Depth

- The system shall reject placing a group under a parent when the result would exceed 2 nesting levels.
- The system shall reject moving a group when the move would exceed 2 nesting levels for the group or any of its descendants.
- Invariant: no group has more than 2 ancestor levels.
- Failure behavior: on rejection, the group hierarchy stays unchanged and the actor learns that the depth limit is the reason.

**Source FS**: GRP-FS-STRUC-002
```

The SRS item adds the move case, the invariant, and the failure outcome. It names no endpoint, error code, or storage.

### Wording to avoid

| Avoid (mechanism) | Write instead (contract) |
|-------------------|--------------------------|
| "Return error code 409" | "Reject the change and leave the entity unchanged" |
| "Return RoleId and Version" | "Make the role identity and its current version available to the actor" |
| "Publish to topic X" / "call service Y" | "Make the change observable to [stakeholder]" / "obtain [fact] from [system]" |
| "Store in table X" | "Retain [entity] for [period]" |
| "Increment the version column" | "Each accepted change produces a new version of [entity]" |

---

## Filtering Process Output

```markdown
## Included Requirements

| FS ID | FS Item | Kind | Extracted / As-is |
|-------|---------|------|-------------------|
| GRP-FS-STRUC-002 | Limit nesting to 2 levels | Business rule | As-is, then refined |
| GRP-FS-TCHR-015 | When member selected and Delete clicked, remove member | Lifecycle (hybrid) | Remove member from Teacher Group |

## Excluded Requirements

| FS ID | FS Item | Reason |
|-------|---------|--------|
| GRP-FS-TCHR-016 | Display Teacher Group at top of list | UI ordering |
| GRP-FS-TCHR-006 | Prevent selection for bulk operations | UI interaction only |
```

---

## Checklist

For each FS item:

- [ ] Does it imply a system guarantee (lifecycle, rule, authorization, retrieval, state, external dependency, observable effect, quality)?
- [ ] Is it only UI presentation? Then exclude it.
- [ ] If hybrid, is the UI part removed from the extracted guarantee?
- [ ] Are all Step 3 questions answered or recorded as "none"?
- [ ] Is the wording free of endpoints, error codes, payload fields, transports, topics, storage, and libraries?
