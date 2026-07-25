# CUD Constraints

Patterns for documenting Create/Update/Delete constraints and their DynamoDB implementations.

---

## Constraint Types

| Constraint Type | DynamoDB Implementation | Example |
|-----------------|------------------------|---------|
| **Uniqueness** | `PUT WHERE not_exists(PK)` or dedicated uniqueness table in transaction | GroupId unique within org |
| **Existence** | `UPDATE WHERE exists(PK)` or `ConditionCheck` | Group must exist before update |
| **State guard** | `Condition + attribute == expected_value` | COOA status must be ACTIVE |
| **Referential integrity** | `ConditionCheck` in transaction | Verify parent exists when creating child |
| **Count-based** | `Condition + size(set) > 0` or counter attribute check | At least 1 FAI if DSI exists |
| **Immutability** | Application-side: exclude field from UpdateExpression | GroupId cannot change after creation |
| **Cross-entity** | Transaction with multiple ConditionChecks | Create FAI only if COOA is ACTIVE |

---

## Documentation Format

```markdown
# CUD Constraints

| Use Case | Constraints | DynamoDB Implementation |
|----------|-------------|----------------------|
| Create [Entity] | * [constraint 1] | [How: condition / transaction / app-side] |
|                  | * [constraint 2] | [How] |
| Update [Entity] | * [constraint] | [How] |
| Delete [Entity] | * [constraint] | [How] |
```

---

## Common Constraint Patterns

### Create with Uniqueness
```
| Create Group | * GroupId unique within org | PUT WHERE not_exists(PK={orgId}, SK=G#{groupId}) |
|              | * GroupAccountId globally unique | PUT accountId WHERE not_exists(PK) in transaction |
```

### Create with Marker Item Uniqueness (Single-Table)

In single-table designs, use marker items for atomic uniqueness within a `TransactWrite`:

```
| Create Group | * GroupId unique within org | TransactWrite: PUT WHERE not_exists(pk=G#{uuid}, sk=G) |
|              | * GroupAccountId cross-service unique | TransactWrite: PUT marker WHERE not_exists(pk=ACC#{accountId}, sk=ACC) |
```

The marker item and entity are created atomically — if either exists, the entire transaction fails. This avoids race conditions that could occur with separate uniqueness checks followed by writes.

See [DynamoDB-Patterns.md — Marker Items for Atomic Uniqueness](./DynamoDB-Patterns.md#marker-items-for-atomic-uniqueness-single-table) for full pattern details.

### Update with Immutability
```
| Update Group | * GroupId immutable | Application-side: exclude from UpdateExpression |
|              | * Group must exist | UPDATE WHERE exists(PK) |
```

### Delete with Guards
```
| Delete Group | * Cannot delete Teacher Group | Application-side: check isSystemGroup before DELETE |
|              | * confirm=true required | Application-side validation |
```

### Create with Referential Check
```
| Add Member | * User must exist in org | Call Identity API (external) |
|            | * No circular reference | Application-side graph traversal |
|            | * Not already a member | PUT WHERE not_exists(PK+SK) |
```
