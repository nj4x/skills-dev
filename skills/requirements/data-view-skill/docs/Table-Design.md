# Table Design Conventions

Conventions for defining DynamoDB table schemas in Data View documents.

---

## Table Definition Format

For each table, document:

1. **Purpose** — one-line description
2. **Schema** — PK, SK, and all attributes with types
3. **Field Descriptions** — detailed description of each field
4. **GSIs** — if any

---

## Naming Conventions

Follow your team's DynamoDB Naming Convention for all table, GSI, and attribute names.

### Table Names
- Format: `<app_prefix>_<submodule>_<descriptor>`
- Prefix: `dev_` (dev), `stg_` (staging), `prd_` (production)
- Example: `dev_group_group`, `dev_group_membership`

### GSI Names
- Format: `<submodule>_<gsi_descriptor>_gsi` (snake_case)
- `<gsi_descriptor>` should describe the GSI's PK, PK+SK, or purpose
- Example: `group_id_gsi`, `group_member_id_gsi`
- **Do NOT use numbered GSI names** (e.g., `GSI1`, `GSI2`) — use descriptive names for readability

### Attribute Names
- Table PK/SK: use `PK` and `SK` (uppercase) as column names
- All other attributes: **camelCase** (e.g., `groupName`, `createdAt`, `orgId`)
- Use common abbreviations (e.g., `orgId` not `organizationId`)
- Avoid unnecessary qualifiers
- GSI PK/SK attributes: if not overloaded, use the specific attribute name (e.g., `userId`). If overloaded, use `<gsi_descriptor>Gsipk` / `<gsi_descriptor>Gsisk`

### Enum Values
- ALL_CAPS with underscores: `ACTIVE`, `PENDING_FEDERATION`, `ADD_MEMBERS`

### Hierarchical/Overloaded PK/SK Values
- ALL_CAPS separated by `#`: `CANADA#BC#VANCOUVER`, `ROLE#ADMIN#user123`

## Key Design Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| **PK/SK column names** | Uppercase `PK` and `SK` | `PK (S)`, `SK (S)` |
| **SK Prefix** | Use `#` delimiter with entity type prefix | `G#{groupId}`, `U#{userId}`, `B#{batchId}` |
| **Composite keys** | Use `#` delimiter, ALL_CAPS for type prefix | `ROLE#ADMIN#user123` |
| **GSI naming** | `<submodule>_<descriptor>_gsi` (snake_case) | `group_id_gsi`, `group_member_id_gsi` |
| **Attribute types** | S=String, N=Number, B=Binary, BOOL=Boolean, M=Map, L=List, SS=String Set | Document in parentheses |
| **Enum values** | ALL_CAPS with underscores | `OWNER`, `MANAGER`, `MEMBER` |

---

## PK/SK Prefix Strategy

### PK Prefixes (Single-Table Designs)

In single-table designs where multiple entity types share one table, use **PK prefixes** to identify entity type at the partition key level:

| Prefix | Entity Type | Example PK | When to Use |
|--------|------------|------------|-------------|
| `G#` | Group | `G#550e8400-...` | Group entity and all its sub-items (members, counts, batches) |
| `ACC#` | Account marker | `ACC#teacher@domain.com` | Uniqueness marker items |
| `U#` | User | `U#user-uuid-123` | User-scoped partitions |

**Convention**: Use short, 1-3 character prefixes followed by `#`. The prefix identifies the entity type; the value after `#` is the entity's identifier.

**When to use PK prefixes**:
- **Single-table design**: Always — prevents PK collisions between entity types
- **Multi-table design**: Not needed — each table contains one entity type

### SK Prefixes

Use SK prefixes to enable efficient filtering within a partition:

| Prefix | Entity Type | Example SK |
|--------|------------|------------|
| `G` | Main group entity | `G` (single character for main item) |
| `G#C#` | Regional count | `G#C#US`, `G#C#EU` |
| `M#U#` | User member | `M#U#user-uuid-123` |
| `M#G#` | Group member | `M#G#child-group-id` |
| `BA#` | Batch job | `BA#batch-uuid-456` |
| `ACC` | Account marker | `ACC` (single value for marker item) |

Benefits:
- `begins_with(sk, "M#U#")` → get only USER members
- `begins_with(sk, "M#G#")` → get only GROUP members (unambiguous)
- `begins_with(sk, "G#C#")` → get all regional counters
- Short prefixes keep SK size small (1024 byte limit)

### Prefix Abbreviation Registry

When using short prefixes, document all abbreviations at the top of the Data View for reference:

```markdown
Prefixes: G#=Group, M#=Membership, C#=Count, BA#=Batch, ACC#=Account, U#=User
```

---

## Entity Type Discriminator Attribute

In single-table or overloaded designs, add an `entityType` attribute to every item:

| entityType Value | Item Type | Description |
|-----------------|-----------|-------------|
| `GROUP` | Main group entity | Core group record |
| `COUNT` | Regional counter | Per-region member count |
| `USER` | User membership | User-to-group relationship |
| `GROUP_MEMBER` | Group membership | Group-to-group relationship |
| `BATCH` | Batch job | Async batch operation record |
| `GROUP_ACCOUNT_ID` | Uniqueness marker | Cross-service uniqueness guard |

**Why**: Application code can dispatch on `entityType` instead of parsing SK prefix strings. Cleaner code, less error-prone than regex on sort keys.

**Convention**: Use `entityType` as the standard attribute name. Values should be ALL_CAPS matching the entity concept.

---

## Business ID vs System ID Naming

When an entity has both a user-defined business identifier and a system-generated UUID, disambiguate clearly:

| Concept | Naming Convention | Example | Description |
|---------|------------------|---------|-------------|
| System ID | `id` | `id` (UUID) | System-generated unique identifier, used as `{id}` path parameter |
| Business ID | `[entity]BusinessId` | `groupBusinessId` | User-defined identifier (e.g., "engineering-team") |

**Why**: Avoid ambiguous names like `groupId` that could mean either the UUID or the business identifier. This confusion was identified in practice when readers couldn't tell if `groupId` referred to the UUID partition key or the user-defined business ID.

**Rule**: If an entity has both identifiers, the business ID MUST include `Business` in the name. The system UUID is simply `id`.

---

## GSI Documentation

For each GSI:

```markdown
| GSI Name | PK | SK | Projection | Purpose |
|----------|----|----|------------|---------|
| [name] | [attribute] | [attribute or —] | ALL / KEYS_ONLY / INCLUDE [...] | [Which access pattern(s) this supports] |
```

### GSI Design Rules

1. **Every GSI must be justified** by a specific access pattern
2. **Prefer KEYS_ONLY** projection unless the access pattern needs full item attributes
3. **Use ALL projection** when the GSI is used for listing/filtering and the caller needs most attributes
4. **Sparse indexes** — only populate GSI attributes on qualifying items to save storage
5. **No orphan GSIs** — if no access pattern uses it, remove it

---

## Schema Documentation Format

```markdown
## [Table Name] Table

[Purpose: one line]

### Schema

| PK (S) | SK (S) | attr1 (type) | attr2 (type) | ... |
|--------|--------|-------------|-------------|-----|
| [pattern] | [pattern] | [description] | [description] | |

### Field Descriptions

* **PK**: [description of what the partition key represents]
* **SK**: [description of what the sort key represents and its prefix convention]
* **attr1**: [description, constraints, default value, enum values if applicable]
* **attr2**: [description]
```

---

## DynamoDB Limits to Consider

| Limit | Value | Impact |
|-------|-------|--------|
| Item size | 400 KB max | Large arrays (e.g., batch members) may need S3 offloading |
| Transaction items | 100 max | Complex transactions may need splitting |
| Partition throughput | 3000 RCU / 1000 WCU per partition | Hot partition risk for high-traffic keys |
| GSI count | 20 per table | Plan GSIs carefully |
| SK size | 1024 bytes max | Keep SK values concise |
