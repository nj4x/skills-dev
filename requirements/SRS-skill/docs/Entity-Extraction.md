# Entity Extraction Guide

This document provides rules and patterns for extracting entities and their attributes from Feature Set (FS) requirements when creating SRS documents.

## What is an Entity?

An **entity** is a core domain object that:
- Is created, read, updated, or deleted by the system
- Has identifiable attributes (properties)
- Has relationships to other entities
- Persists in data storage

## Entity Identification Patterns

### Pattern 1: CRUD Operation Targets

Look for nouns that are targets of CRUD operations:

| FS Pattern | Entity Candidate |
|------------|------------------|
| "The system shall create a [noun]" | [noun] is an entity |
| "The system shall store [noun]" | [noun] is an entity |
| "The system shall delete [noun]" | [noun] is an entity |
| "The system shall update [noun] properties" | [noun] is an entity |

**Examples:**
- "The system shall create a new **system role**" → Entity: `SystemRole`
- "The system shall store **group** information" → Entity: `Group`
- "The system shall delete **membership** records" → Entity: `Membership`

### Pattern 2: Unique Identifier Mentions

Entities typically have unique identifiers:

| FS Pattern | Entity Candidate |
|------------|------------------|
| "[Noun]Id" or "[Noun] ID" mentioned | [Noun] is likely an entity |
| "unique identifier for [noun]" | [noun] is an entity |

**Examples:**
- "The system shall generate a unique **RoleId**" → Entity: `Role`
- "The system shall use **GroupId** as primary identifier" → Entity: `Group`

### Pattern 3: Attribute Collections

When multiple attributes are described together:

| FS Pattern | Entity Candidate |
|------------|------------------|
| "The system shall take [attr1], [attr2], [attr3] as inputs" | Parent noun is an entity |
| "The system shall return [attr1], [attr2] in response" | Parent noun is an entity |

**Examples:**
- "take **RoleName**, **RoleDescription**, **PrivilegeList** as inputs" → Entity: `Role`
- "return **GroupId**, **GroupName**, **MemberCount**" → Entity: `Group`

### Pattern 4: State or Status Tracking

Entities often have states:

| FS Pattern | Entity Candidate |
|------------|------------------|
| "[noun] status" | [noun] is an entity |
| "[noun] state transitions" | [noun] is an entity |
| "active/inactive [noun]" | [noun] is an entity |

---

## Attribute Extraction Patterns

### Pattern A: Input Parameters

```
"The system shall take [X], [Y], [Z] as inputs"
```

Extract: X, Y, Z are attributes

**Example:**
```
"The system shall take RoleName, RoleDescription(optional), PrivilegeList as inputs"
```
Extracted attributes:
- `RoleName` (required)
- `RoleDescription` (optional)
- `PrivilegeList` (required)

### Pattern B: Output/Response Fields

```
"The system shall return [X], [Y] in the response"
```

Extract: X, Y are attributes

**Example:**
```
"The system shall return the RoleId, and Version:1 in the response"
```
Extracted attributes:
- `RoleId` (auto-generated)
- `Version` (auto-generated, default: 1)

### Pattern C: Immutable Flags

```
"The system shall create [an immutable | a fixed | a permanent] [flag/tag] [X]"
```

Extract: X is an immutable attribute

**Example:**
```
"The system shall create an immutable flag IsSystemRole:true"
```
Extracted attribute:
- `IsSystemRole` (auto-generated, immutable, default: true)

### Pattern D: Constraint Descriptions

```
"[Attribute] shall be [constraint]"
"[Attribute] shall not exceed [limit]"
```

Extract: Attribute with constraint metadata

**Examples:**
```
"GroupName shall not exceed 200 characters"
"RoleId shall be immutable after creation"
```
Extracted:
- `GroupName` (max length: 200)
- `RoleId` (immutable: true)

### Pattern E: Uniqueness Requirements

```
"[Attribute] shall be unique within [scope]"
```

Extract: Attribute with uniqueness constraint

**Example:**
```
"GroupId shall be unique within an organization scope"
```
Extracted:
- `GroupId` (unique within: organization)

---

## Attribute Classification

### By Source

| Source Type | Description | Example |
|-------------|-------------|---------|
| **User Input** | Provided by API caller | RoleName, Description |
| **Auto-generated** | Created by system | RoleId, CreatedAt |
| **Derived** | Calculated from other data | MemberCount, PrivilegeCount |

### By Mutability

| Type | Description | Example |
|------|-------------|---------|
| **Immutable** | Cannot change after creation | RoleId, IsSystemRole |
| **Mutable** | Can be updated | RoleName, Description |
| **Append-only** | Can add but not remove | AuditLog |

### By Requirement

| Type | Description | Example |
|------|-------------|---------|
| **Required** | Must be provided | RoleName, PrivilegeList |
| **Optional** | May be omitted | Description |
| **Conditional** | Required in certain contexts | RootOUId (for custom roles) |

---

## Entity Documentation Template

### Entity Definition Table

```markdown
## Entity: [EntityName]

| Attribute | Type | Source | Required | Immutable | Constraints | Description |
|-----------|------|--------|----------|-----------|-------------|-------------|
| [name] | [type] | [source] | Yes/No | Yes/No | [constraints] | [description] |
```

### Example: SystemRole Entity

```markdown
## Entity: SystemRole

| Attribute | Type | Source | Required | Immutable | Constraints | Description |
|-----------|------|--------|----------|-----------|-------------|-------------|
| RoleId | UUID | Auto | Yes | Yes | Unique globally | Primary identifier |
| RoleName | String | Input | Yes | No | Max 200 chars | Display name |
| RoleDescription | String | Input | No | No | Max 1000 chars | Optional description |
| PrivilegeList | Array | Input | Yes | No | Non-empty | List of privilege IDs |
| IsSystemRole | Boolean | Auto | Yes | Yes | Always true | System role marker |
| Version | Integer | Auto | Yes | No | Starts at 1, increments | Version tracking |
| CreatedAt | DateTime | Auto | Yes | Yes | ISO 8601 | Creation timestamp |
| UpdatedAt | DateTime | Auto | Yes | No | ISO 8601 | Last update timestamp |
```

---

## Entity Relationship Patterns

### One-to-Many

```
"A [EntityA] can have multiple [EntityB]s"
"Each [EntityA] contains zero or more [EntityB]s"
```

**Example:**
```
"A Group can have multiple Members"
```
Relationship: Group (1) → Member (*)

### Many-to-Many

```
"A [EntityA] can belong to multiple [EntityB]s"
"[EntityA]s and [EntityB]s have a many-to-many relationship"
```

**Example:**
```
"A User can belong to multiple Groups"
"A Group can have multiple Users"
```
Relationship: User (*) ↔ Group (*) via Membership

### Hierarchical

```
"[EntityA] can contain other [EntityA]s"
"[EntityA] supports nesting up to [N] levels"
```

**Example:**
```
"Groups can contain other Groups as members"
"Group nesting limited to 2 levels"
```
Relationship: Group → Group (self-referential, max depth: 2)

---

## Common Entity Types in SRS

### Primary Entities
Core business objects managed by the system:
- `Role`, `Group`, `User`, `Organization`, `Permission`

### Junction Entities
Represent many-to-many relationships:
- `Membership` (User-Group relationship)
- `RoleAssignment` (User/Group-Role relationship)
- `PermissionGrant` (Role-Permission relationship)

### Audit Entities
Track changes and history:
- `AuditLog`, `ChangeHistory`, `AccessLog`

### Configuration Entities
System settings and policies:
- `Policy`, `Configuration`, `Setting`

---

## Extraction Checklist

When analyzing FS requirements, systematically check:

- [ ] What nouns are targets of CRUD operations?
- [ ] What identifiers are mentioned (XxxId)?
- [ ] What attributes are listed as inputs?
- [ ] What attributes are returned in responses?
- [ ] What immutable flags/tags are created?
- [ ] What constraints are specified (length, uniqueness)?
- [ ] What relationships exist between entities?
- [ ] What auto-generated fields are mentioned?

---

## Anti-Patterns: Not Entities

These are typically NOT entities:

| Pattern | Reason | Example |
|---------|--------|---------|
| UI elements | Front-end only | Button, Modal, Form |
| Actions/Verbs | Operations, not objects | Create, Update, Validate |
| Temporary data | Not persisted | Session, Request |
| Aggregations | Derived, not stored | TotalCount, Statistics |
| External systems | Out of scope | ExternalAPI, ThirdPartyService |