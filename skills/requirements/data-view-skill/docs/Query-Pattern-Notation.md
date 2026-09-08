# Query Pattern Notation

Conventions for documenting DynamoDB query patterns in Data View documents.

---

## Operation Notation

Use these standard notations consistently:

| Operation | Notation | Example |
|-----------|----------|---------|
| **Get Item** | `GET [table] WHERE PK={val} AND SK={val}` | `GET group WHERE PK={orgId} AND SK=G#{groupId}` |
| **Put Item** | `PUT [table] WHERE not_exists(PK)` | `PUT group WHERE not_exists(PK) * PK={orgId} * SK=G#{groupId}` |
| **Update Item** | `UPDATE [table] WHERE exists(PK)` | `UPDATE group WHERE exists(PK) * PK={orgId} AND SK=G#{groupId}` |
| **Delete Item** | `DELETE [table] WHERE exists(PK)` | `DELETE group WHERE PK={orgId} AND SK=G#{groupId}` |
| **Query** | `QUERY [table/gsi] WHERE PK={val}` | `QUERY membership WHERE PK={groupId}` |
| **Query with filter** | `QUERY [table] WHERE PK={val} FILTER BY [cond]` | `QUERY group WHERE PK={orgId} FILTER BY isSystemGroup=true` |
| **Batch Get** | `BatchGetItem [table] WHERE PK={val} AND SK={val} for each` | `BatchGetItem group for each groupId` |
| **Scan** | `SCAN [table]` | `SCAN cooa` (avoid if possible) |
| **Condition Check** | `ConditionCheck [table] WHERE PK={val}` | `ConditionCheck cooa WHERE PK={type} * status == ACTIVE` |
| **Transaction** | `Transactional Write` + numbered items | See below |

---

## Attribute Listing

When documenting attributes being written, use bullet points:

```
PUT group WHERE not_exists(PK)
  * PK={orgId}
  * SK=G#{groupId}
  * id={uuid}
  * groupName={groupName}
  * createdAt={now}
```

---

## Transaction Notation

Number each operation in the transaction:

```
Transactional Write:
  1. PUT group WHERE not_exists(PK)
     * PK={orgId}, SK=G#{groupId}
  2. PUT accountId WHERE not_exists(PK)
     * PK={groupAccountId}
  3. PUT groupById WHERE not_exists(PK)
     * PK={uuid}
```

---

## Multi-Step Use Cases

For use cases with multiple steps, use the 4-column table format:

```markdown
| Use Case | Steps | Query Patterns | Notes |
|----------|-------|----------------|-------|
| Create group | 1. Validate domain | Call Organization API | External dependency |
| | 2. Check uniqueness | GET accountId WHERE PK={accountId} | |
| | 3. Transactional Write | 1. PUT group ... | See transaction above |
| | | 2. PUT accountId ... | |
| | 4. Publish event | Kafka: event.group.group | |
```

---

## Annotations

| Annotation | Meaning |
|------------|---------|
| `(external dependency)` | Requires API call to another service |
| `Application-side` | Logic handled in code, not DynamoDB |
| `Async:` | Operation performed asynchronously (event-driven) |
| `for_each:` | Iteration over query results |
| `*Consider...*` | Design suggestion (italic) |
