# Denormalization Strategy

Framework for evaluating denormalization decisions in DynamoDB Data View design.

---

## When to Denormalize

DynamoDB has no JOIN. Every query returns data from a single table/GSI partition. If a read requires data from multiple entities, you must either:
1. **Denormalize**: Copy data into the read location (faster reads, more complex writes)
2. **Application-side join**: Multiple queries + code to combine results (simpler writes, slower reads)

---

## Decision Framework

For each candidate denormalization, evaluate:

| Factor | Question | Favor Denormalize | Favor Normalize |
|--------|----------|-------------------|-----------------|
| **Read frequency** | How often is the combined data read? | Very frequently (every request) | Rarely |
| **Write frequency** | How often does the source data change? | Rarely | Frequently |
| **Consistency requirement** | Is stale data acceptable? | Yes (eventual OK) | No (must be current) |
| **Fan-out cost** | How many items need updating when source changes? | Few items (bounded) | Many items (unbounded) |
| **Data size** | How much data is being duplicated? | Small (a few attributes) | Large (complex objects) |

---

## Documentation Format

For each denormalization decision in the Data View:

```markdown
* Should [attribute/relationship] be denormalized?
  + Recommendation: YES / NO
  + Denormalized
    - [Read benefit: e.g., "single query returns complete data"]
    - [Consistency requirement: e.g., "required for transactional integrity"]
  + Normalized
    - [Write benefit: e.g., "simple single-table write"]
    - [Read cost: e.g., "requires application-side join with 2 queries"]
  + Decision: [Chosen approach and rationale]
```

---

## Common Denormalization Scenarios

### Display Name in Membership Records — Decision Fork

The correct decision depends on **how the display name is used**:

**If display name is only needed for display (rendering in API responses)**:
- **Decision: Do NOT denormalize**
- User/group names change independently
- Fan-out is unbounded (user could be in hundreds of groups)
- Read-time fetch from source service is acceptable

**If display name is needed for search/filter/sort (e.g., `query` parameter prefix search)**:
- **Decision: MUST denormalize**
- DynamoDB cannot filter on data it doesn't have — search breaks without the attribute
- Store `displayName` and `displayNameLower` on each record
- Add a GSI with `displayNameLower` as SK for prefix search (`begins_with`)
- Keep fresh via event-driven updates: consume name-change events (e.g., `UserProfileUpdated`, `GroupUpdated`)
- Fan-out is bounded per-entity (a user's name change updates only their ~10-50 membership records)
- **Trade-off**: Eventually consistent — brief window where searches return stale names after a change

### Status from Related Entity
**Decision: Evaluate carefully**
- If status is checked on every read → consider denormalizing
- If status changes cascade to many records → do NOT denormalize
- Example: FAI status depends on COOA status → normalize (COOA affects all orgs)

### Count Attributes
**Decision: Denormalize as counter**
- Maintain counter on parent entity (e.g., memberCount on Group)
- Update atomically with ADD operation
- Avoids counting query on every read

> **⚠️ DynamoDB Enhanced Client Limitation**: The DynamoDB Enhanced Client does not support `UpdateExpression` (including atomic `ADD` operations) within `TransactWriteItems`. To atomically increment counters in transactions, use one of:
> 1. **Low-level DynamoDbClient** — supports `ADD count :val` in transaction UpdateExpressions directly, but requires manual data mapping (more verbose code)
> 2. **Enhanced Client with versioning** — use read-modify-write pattern with `@DynamoDbVersionAttribute` to prevent concurrent counter corruption. Simpler code but adds a read operation before write.

### Denormalized Snapshot Objects (Map Attributes)

When a related entity's details are needed in API responses and the related entity is relatively stable, denormalize a **snapshot** as a Map (M) attribute containing multiple fields:

```
Membership item for GROUP member:
  pk=G#{parentGroupId}, sk=M#G#{memberGroupId}
  groupMember (M) = {
    groupBusinessId: "engineering-team",
    domain: "corp.com",
    groupAccountId: "engineering-team@corp.com",
    name: "Engineering Team",
    description: "All engineers"
  }
```

**When to use snapshot objects vs individual attributes**:

| Approach | When to Use | Trade-offs |
|----------|-------------|------------|
| **Snapshot object (Map)** | Multiple fields from related entity needed in API response; fields are mostly read-only; source entity changes infrequently | Simpler read (one attribute); atomic update of entire snapshot; but wastes write if only one field changes |
| **Individual attributes** | Only 1-2 fields needed (e.g., just `displayName`); field is used in GSI sort key; field needs independent update frequency | Each field independently updatable; can be GSI SK; but multiple attributes to manage |

**Refresh strategy**: Keep snapshot fresh via event-driven updates — consume entity-change events (e.g., `GroupUpdated`) and overwrite the entire Map attribute. Simpler than tracking individual field changes.

**Note**: Snapshot objects cannot be used as GSI sort keys. If you need to search/sort by a field within the snapshot, extract it as a top-level attribute.

### Computed Values from Immutable Components
**Decision: Do NOT store — compute at read time**
- If components are immutable, computation is always correct
- Example: GroupAccountId = GroupId + "@" + GroupDomain (both immutable)
