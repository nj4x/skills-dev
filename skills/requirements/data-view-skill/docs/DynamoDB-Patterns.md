# DynamoDB Design Patterns

Reference guide for common DynamoDB patterns used in Data View design.

---

## Access Pattern-Driven Design

**CRITICAL**: DynamoDB table design is driven by access patterns, NOT entity relationships.

1. List ALL access patterns from SRS/API Definition
2. Group by read/write frequency
3. Design PK/SK to support the most common patterns
4. Use GSIs for secondary access patterns
5. Consider denormalization to avoid JOINs (DynamoDB has no JOIN)

---

## Partition Key Selection

| Criterion | Guidance |
|-----------|----------|
| **Cardinality** | High cardinality preferred (avoid hot partitions) |
| **Query isolation** | PK should scope queries to a single tenant/org for multi-tenant systems |
| **Item collection** | Items queried together should share a PK |
| **Write distribution** | Writes should distribute evenly across partitions |

---

## Common Patterns

### One-to-Many
Parent with multiple children sharing the same partition key.
```
PK = parentId
SK = childPrefix#childId
```
Example: Group table — PK=orgId, SK=G#{groupId}

### Many-to-Many (Junction Table)
Separate table for the relationship with GSI for reverse lookup.
```
Base: PK=groupId, SK=U#{userId}
GSI:  PK=userId,  SK=groupId (reverse lookup)
```

### UUID Lookup
Separate lookup table to resolve UUID to natural keys.
```
GroupById Table: PK=uuid → returns orgId, groupId
```
Used when APIs accept UUID but the primary table uses composite natural keys.

### Uniqueness Enforcement
Dedicated table where PK = the value that must be unique.
```
AccountId Table: PK=groupAccountId (must be globally unique)
PUT WHERE not_exists(PK) — fails if duplicate
```

### Marker Items for Atomic Uniqueness (Single-Table)

In single-table designs, use **marker items** within the same table instead of a separate uniqueness table. This enables atomic uniqueness validation within a `TransactWrite` alongside the entity creation — no external API call needed.

```
Entity item:   pk=G#{uuid}, sk=G
Marker item:   pk=ACC#{groupAccountId}, sk=ACC

TransactWrite:
  1. PUT entity WHERE not_exists(pk+sk)     → creates the entity
  2. PUT marker WHERE not_exists(pk+sk)     → reserves the unique value atomically
```

**Convention**:
- PK prefix identifies the marker type (e.g., `ACC#` for account IDs)
- SK is a short fixed value (e.g., `ACC`) — the uniqueness is enforced on the PK
- Include `entityType` attribute (e.g., `GROUP_ACCOUNT_ID`) for discoverability
- Include `createdAt` and `createdBy` for audit trail

**When to use marker items vs external API calls**:
- **Marker item**: When the unique value is owned by this service and atomicity is needed
- **External API call**: When the unique value spans multiple services (e.g., checking user account IDs owned by Identity service)

### Metadata / Constraint Item
Separate item to track counts or sets for cross-entity constraints.
```
PK=orgId, SK=METADATA
Attributes: faiCount, domainCount, dsiCount
```
Used when constraints span multiple entities (e.g., "at least 1 FAI if DSI exists").

### Sparse Index
GSI populated only on qualifying items. Items without the GSI attribute are excluded.
```
GroupRoleCache: Only groups with assigned admin roles have entries
```

---

## Transaction Patterns

DynamoDB transactions support up to 100 items across tables:

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Create with uniqueness** | PUT entity + PUT uniqueness guard | Create group + reserve GroupAccountId |
| **Create with constraint** | PUT entity + UPDATE metadata | Create FAI + increment faiCount |
| **Delete with cleanup** | DELETE entity + DELETE related records | Delete group + delete accountId + delete UUID lookup |
| **Cross-entity consistency** | Multiple operations with condition checks | Save FAI + verify COOA is ACTIVE |

---

## Pagination (Tag-based)

```
Client → GET /v2/groups?pageSize=20
Server → QUERY with Limit=20
       → Encode lastEvaluatedKey as base64 → nextPageTag
       → Return { items: [...], nextPageTag: "eyJ..." }

Client → GET /v2/groups?pageSize=20&pageTag=eyJ...
Server → Decode pageTag → exclusiveStartKey
       → QUERY with Limit=20 and ExclusiveStartKey
```

---

## FilterExpression Semantics: `Limit` Applies Before Filter

**Critical gotcha**: DynamoDB's `Query` `Limit` is a cap on the number of items *scanned*, not the number of items *returned after filtering*. If you use `.limit(1)` with a `FilterExpression`, DynamoDB reads at most 1 item from storage, applies the filter, and returns 0 or 1 results — meaning a `limit(1)` check can return zero matches even when matching items exist further in the partition.

This causes silent correctness bugs: an existence check appears to pass ("no matches") when blocking matches are present beyond the first scanned row.

### Correct patterns

**Existence check** — omit `Limit`; use the SDK's lazy `PageIterable` and stop at the first match:
```kotlin
// Correct: never uses Limit; stops fetching on first matching item
val exists = assignmentTable.query(builder.build())
    .flatMap { it.items() }
    .firstOrNull() != null
```

**Counting** — accumulate across all pages:
```kotlin
// Correct: sums across all pages, no Limit
val count = assignmentTable.query(builder.build()).sumOf { it.items().size }
```

For count-only queries, project just the key attributes (`attributesToProject("PK", "SK")`) so the Enhanced Client transfers and deserializes near-empty items instead of full rows. **Caveat**: this reduces network payload and client-side CPU, *not* RCU — DynamoDB bills on items scanned *before* filter/projection. The server still applies any `FilterExpression` against the full stored item, so filter attributes need not be projected. The truly payload-free form is `Select=COUNT`, but the Enhanced Client (`DynamoDbTable`) doesn't expose it — that requires the low-level `DynamoDbClient`.

**Prefer natural-key SK prefixes over FilterExpression** — when the discriminating value is encoded in the sort key (e.g. `scopeType` as a SK component, or `begins_with(SK, "A#{roleId}#")`), DynamoDB narrows the scan at the storage layer with no filter. Use `FilterExpression` only when the discriminator cannot be expressed in the key condition.

**When `Limit` is safe** — only when there is **no** `FilterExpression` on the query, e.g. a raw existence check on the PK/SK alone (`existsAnyAssignmentForSystemRole` uses `Limit=1` via `role_assignment_by_role_gsi` with no filter — the GSI itself is sparse, so every item in that partition is a match).

---

## Async Cascade Patterns

When an operation triggers expensive cascading updates:

1. **Self-consuming event**: Publish event → consume it yourself for async processing
2. **Pending status**: Set intermediate status before async job starts
3. **Idempotent handlers**: Design handlers to safely re-process the same event

---

## Hierarchical Traversal (Recursive Expansion)

**Problem**: APIs may require recursive traversal of hierarchical data (e.g., `expand=true` on nested groups, org trees, folder structures, permission inheritance). DynamoDB has no native recursive query.

### Pattern: BFS at Query Time (Phase 1)

Use Breadth-First Search with repeated DynamoDB Queries:

```
Downward traversal (parent → children):
  QUERY base_table WHERE pk={parentId}  →  all children
  For each GROUP-type child: enqueue for next level

Upward traversal (child → parents):
  QUERY reverse_gsi WHERE pk={childId}  →  all parent groups
```

**Considerations**:
- **Depth safety limit**: Configurable circuit breaker (e.g., 100 levels) — not a business rule. Prevents runaway queries.
- **De-duplication**: Track visited nodes in a Set. If an entity is reachable via multiple paths, return it once (shallowest path wins).
- **Pagination**: DDB's native pagination only works per-query. For multi-query results, the application must manage its own cursor (encode BFS state in opaque `nextPageTag`).
- **Response enrichment**: Fields like `isDirect`, `sourceGroupId` are computed at application layer — NOT stored in DDB.

### Pattern: Materialized Expansion (Phase 2 — Pre-computed)

For high-frequency expanded queries, pre-compute flattened results:

```
Write Path (event-driven):
  On MemberAdded event:
    Walk ancestor chain via reverse_gsi (upward traversal)
    For each ancestor: write EXPANDED#{memberId} item
  On MemberRemoved event:
    Reverse — delete EXPANDED# items from all ancestors

Read Path:
  QUERY base_table WHERE pk={parentId}
  → Returns both direct items AND EXPANDED# items in one query
  → O(1) read complexity
```

**Trade-offs**:

| Aspect | BFS (Phase 1) | Materialized (Phase 2) |
|---|---|---|
| Read latency | O(depth × breadth) queries | O(1) single query |
| Write cost | None | Write amplification on changes |
| Consistency | Always fresh | Eventually consistent |
| Complexity | Simple app logic | Complex event handler |
| Pagination | Application-managed cursor | Native DDB pagination |

**Recommendation**: Start with Phase 1. Monitor query latency. If it becomes a bottleneck, implement Phase 2. Schema supports both — no migration needed.

### Cleanup on Delete (Hard Delete)

When deleting parent entities that have associated counter items (e.g., `COUNT#` items from the Per-Region Counter pattern), the delete operation MUST also clean up those items:

```
QUERY table WHERE pk={parentId} AND begins_with(sk, "COUNT#"+entityId+"#")
→ BatchWriteItem DELETE for each COUNT# item found
```

This cleanup can be synchronous (as part of the delete) or included in the async cascade, depending on consistency requirements.

---

## Global Table Conflict Resolution — Per-Region Item Pattern

**Problem**: DynamoDB Global Tables use "last writer wins" at the **item level**. If two regions update the same item concurrently, one write is lost. This affects counters, aggregations, and any attribute updated by multiple regions.

**Solution**: Use separate items per region for frequently-updated values.

### Pattern: Per-Region Counter Items + Inline Sum

```
Write Path (inline — same code path as entity write):
  1. Write the entity (e.g., PUT Membership)
  2. Each region writes ONLY to its own count item:
     pk={parentId}, sk=COUNT#{entityId}#REGION_{currentRegion}
     → ADD memberCount :1 (atomic, no conflict)
  3. Immediately read all COUNT# items for this entity:
     QUERY WHERE pk={parentId} AND begins_with(sk, "COUNT#"+entityId)
  4. Sum counts across regions → UPDATE META# SET memberCount=MAX(0, sum)

Batch Optimization:
  For batch operations (e.g., adding 1000 members):
  - Do step 2 (per-region ADD) per item in the batch loop
  - Do steps 3-4 (sum+update META#) ONCE after the batch completes
  - Avoids N sum+update operations; only 1 at the end

Reconciliation Job (daily safety net):
  1. QUERY WHERE pk={parentId} AND begins_with(sk, "COUNT#")
  2. Group by entityId, sum counts across regions
  3. UPDATE pk={parentId}, sk=META#{entityId} SET memberCount=MAX(0, sum)
  Not the primary count mechanism — catches drift from missed updates or edge cases.

Read Path (optimized):
  GET pk={parentId}, sk=META#{entityId}
  → memberCount attribute available directly (cached total)
  → Projected to GSIs — zero extra reads
```

### Variant: Transactional Counter with Version-Based Optimistic Locking

For stronger consistency, wrap the entity write + counter increment in a `TransactWrite` with version checks on the counter item:

```
Write Path (transactional):
  1. Read counter item to get current version:
     GET pk={parentId}, sk=COUNT#REGION_{current}
     → returns {memberCount: N, version: V}

  2. TransactWrite:
     a. PUT Membership WHERE not_exists(pk+sk)
     b. UPDATE COUNT# WHERE pk={parentId} AND sk=COUNT#REGION_{current}
        AND version={V}
        SET memberCount = memberCount + 1, version = version + 1
     → Fails atomically if version changed (concurrent update)

  3. On ConditionalCheckFailedException → retry from step 1
```

**Counter item schema** (when using this variant):

| pk | sk | memberCount (N) | version (N) | lastUpdated (S) |
|----|----|----------------|-------------|----------------|
| parentId | COUNT#REGION_US | 42 | 7 | ISO 8601 |

**When to use transactional counters vs inline non-transactional**:
- **Transactional**: When the entity write and counter MUST be atomic (e.g., membership creation must not succeed without counter increment)
- **Non-transactional (inline)**: When the counter is a display/convenience field with no business constraints, and a daily reconciliation job is acceptable as safety net

### Variant: Event-Driven Total Count Reconciliation (Self-Healing)

Instead of summing counters inline on every write, use an event-driven approach where `MemberAdded`/`MemberRemoved` events trigger a total count recalculation:

```
Event Handler (consume MemberAdded/MemberRemoved):
  1. Query all regional counters:
     QUERY WHERE pk={parentId} AND begins_with(sk, "COUNT#")
  2. Sum memberCount across all regions
  3. Update total on main entity:
     UPDATE pk={parentId}, sk=META#{entityId}
       AND version={expectedVersion}
       SET memberCount=MAX(0, sum)
```

**Self-healing property**: Because the handler always recalculates the total from the authoritative regional counters, it is inherently idempotent and self-correcting. Even if a previous inline update was missed or produced an incorrect total, the next event will fix it.

**When to use**:
- As the **primary** count update mechanism (replaces inline sum)
- Combined with transactional counter increments on the regional items
- The daily reconciliation job still serves as a safety net for missed events

### Negative Per-Region Counts

Individual per-region COUNT# values **can be negative** — this is expected and by design in Global Tables. Example: 5 entities are added in US region (COUNT#...REGION_US = +5), and the same 5 entities are deleted from EU region via cascade (COUNT#...REGION_EU = -5). The total is 0, which is correct, but EU's value is -5. This is normal operation where adds and deletes for the same entities happen in different regions. It can also occur during event replay/retry.

The **sum across all regions** is the correct total count. Always apply `MAX(0, sum)` when writing to the META# item to avoid exposing negative values to API consumers.

### When to Use
- Counters that are incremented/decremented by multiple regions
- Aggregations that need to avoid Global Table write conflicts
- Any attribute where concurrent cross-region updates would cause data loss

### When NOT to Use
- Attributes only written by one region (no conflict)
- Items only created/deleted (PUT with not_exists / DELETE — no conflict)
- Attributes that are immutable after creation

### Trade-offs

| Aspect | Per-Region Items (Inline Sum) | Direct counter on entity |
|--------|-------------------------------|------------------------|
| **Write conflict** | ✅ None (each region owns its item) | ❌ Last writer wins — lost updates |
| **Read cost** | ✅ Zero extra reads (cached total on META#) | ✅ Zero extra reads |
| **Write cost** | Extra COUNT# item per region + inline sum | Single item write |
| **Accuracy** | Near real-time (inline); daily reconciliation safety net | Inaccurate (lost updates) |
| **Complexity** | Inline sum logic in every write path | Simple |
| **Storage** | Extra items per entity per region | No extra items |
