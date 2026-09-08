# Requirement Categorization Guide

## Requirement Types

Requirements can be classified as the following types:

| Type | Abbreviation | Description |
|------|--------------|-------------|
| **Feature Set** | FS | Product outcomes, capabilities, lifecycle behavior, and material safety constraints |
| **Software Requirements Specification** | SRS | System capability, lifecycle, and safety contracts that satisfy FS |

Invocation and realization mechanisms belong in ADRs, not FS/SRS: endpoints, transports, topics, schemas, storage, providers, libraries, modules, and deployment topology. Consult [Requirements boundary](../../../engineering/setup-lineage/SKILL.md#requirements-boundary) before classifying or drafting an item.

> **Note**: SRS should be informed by and adhere to FS.

---

## Category Discovery

Use `search_documents` to identify requirement categories from source documents. Search for topics like:
- CRUD operations
- Membership roles
- Naming policies
- Hierarchy structures
- Authorization rules
- Validation rules

---

## Category Acronyms

Make suitable acronyms for each category (3-5 uppercase letters). Examples (not mandatory or exhaustive - create appropriate acronyms based on actual content):

| Acronym | Category | Description |
|---------|----------|-------------|
| MEMB | Membership | Membership related requirements |
| CRUD | Operations | Create/Read/Update/Delete operations |
| STRUC | Structure | Structure and hierarchy requirements |
| NAME | Naming | Naming and identification policies |
| TYPE | Types | Type classifications |
| ROLE | Roles | Role and permission assignments |
| VALID | Validation | Validation rules |
| AUTH | Authorization | Authorization and access control |

---

## Grouping Guidelines

### Alignment
- Align groupings with source document structure where applicable (e.g., CRUD Operations, Naming Policies, Membership)

### Consistency
- Use consistent naming conventions
- Keep groupings at consistent depth (avoid mixing high-level and granular groupings)
- Requirements within the same category and type should be grouped by related topic
  - e.g., requirements relate to user, or relate to domain

### Hierarchy
```
[Category Acronym]-[Type]-[Grouping]-[Number]

Example: OU-FS-DOMAIN-1
```

Where:
- **Category Acronym**: 3-5 uppercase letters (e.g., GRP, OU, ROLE)
- **Type**: FS (Feature Set) or SRS (Software Requirements Specification)
- **Grouping**: Related topic within the category
- **Number**: Sequential identifier