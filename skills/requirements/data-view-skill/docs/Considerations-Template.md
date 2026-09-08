# Considerations Template

This document defines the required design decisions to evaluate for every Data View.

---

## Required Considerations

Every Data View MUST evaluate and document these decisions:

### 1. Optimistic Locking / Versioning

| Option | Trade-offs |
|--------|-----------|
| **No versioning** | No read-before-write overhead; risk of lost updates on concurrent writes |
| **Selective versioning** | Version only frequently-updated entities; balance between safety and performance |
| **Full versioning** | Safest; forces GET before every UPDATE; DynamoDB Enhanced Client supports this natively |

**Evaluation criteria**: Write frequency, concurrency risk, read-before-write cost.

### 2. Single Table vs Multi-Table

| Option | When to Choose |
|--------|---------------|
| **Single Table** | Entities share a natural partition key; entities are frequently queried together in item collections; simple domain with few entity types |
| **Multi-Table** | Entities have distinct access patterns with different partition keys; high write throughput on one entity type would create hot partitions; GSI design is simpler per table |
| **Hybrid** | Some entities pre-joined in one table (e.g., Group + BatchJob share groupId PK); others in separate tables |

**Evaluation criteria**: Do the primary entities share a natural partition key? Are they queried together? Would one entity's write volume create hot partitions for another?

### 3. Global Tables

For each table, decide: **Global** (multi-region replicated) or **Local** (single-region only).

Most tables will be Global. Only document exceptions or special considerations.

**Default**: All tables are Global Tables unless there's a specific reason not to (e.g., region-specific ephemeral data).

**Note on counters in Global Tables**: If the service has no absolute count restrictions (no min/max constraints on counts), each region can maintain its own copy independently. Sums can be calculated as needed. This avoids complex cross-region write coordination. Services with strict count constraints (e.g., "last admin" checks) may need more careful multi-region write strategies.

### 4. Denormalization Decisions

For each entity relationship, evaluate:

```markdown
* Should [attribute/relationship] be denormalized?
  + Recommendation: YES / NO
  + Denormalized: [read benefit]
  + Normalized: [write benefit]
  + Decision rationale: [why chosen approach]
```

See [Denormalization-Strategy.md](./Denormalization-Strategy.md) for detailed framework.

### 5. TTL Usage

Identify entities that should auto-expire. Evaluate TTL vs explicit cleanup for each:

| Approach | Pros | Cons |
|----------|------|------|
| **DynamoDB TTL** | Zero maintenance; automatic deletion | Eventual (up to ~48h delay); data unrecoverable after deletion; no pre-deletion archival |
| **Explicit cleanup job** | Full control over timing; can archive before deletion; can respect downstream dependencies | Requires scheduled job infrastructure; operational overhead |
| **Event-driven cleanup** | Cleanup triggered after downstream consumer confirms processing (e.g., Activity Tracker acknowledges batch event) | More complex; depends on downstream availability |

**Recommendation**: Use TTL for truly ephemeral data (sessions, tokens). For records that may be referenced by downstream systems (e.g., batch job results referenced by Activity Tracker), prefer explicit cleanup or event-driven cleanup to avoid premature deletion.

Common candidates:
- Session/token data → TTL
- Batch job records → Evaluate: if Activity Tracker owns the permanent record, TTL is acceptable with generous expiry (90+ days)
- Temporary state (pending operations) → TTL

### 6. Pagination Approach

Standard: Tag-based (opaque cursor)
- Encode DynamoDB `lastEvaluatedKey` as base64 → return as `nextPageTag`
- Decode `pageTag` → use as `exclusiveStartKey`

### 7. Search Strategy (DynamoDB vs OpenSearch)

Evaluate whether search/sort/filter operations should be handled by DynamoDB GSIs or offloaded to an external search engine (e.g., OpenSearch):

| Option | When to Choose |
|--------|---------------|
| **DynamoDB GSIs only** | Simple prefix search on 1-2 fields; sort by a single field; small data volume; no full-text search needed |
| **OpenSearch integration** | Full-text search across multiple fields; complex multi-field filtering with boolean logic; advanced sorting (multiple criteria); fuzzy/typo-tolerant search; aggregations/analytics needed |
| **Hybrid** | DynamoDB for transactional reads/writes + point lookups; OpenSearch for search/list/filter/sort operations |

**Evaluation criteria**:
- Does the API require `query` parameter matching across multiple fields (name, ID, description)?
- Is case-insensitive substring search needed (not just prefix)?
- Are there sorting requirements beyond a single GSI SK?
- Do list APIs need complex filtering with boolean logic?

**Impact on Data View**:
- **GSI reduction**: When OpenSearch handles search, GSIs used only for sort/search can be removed (document as `REMOVED` with reason)
- **Access Pattern table**: Mark operations handled by OpenSearch as `**OpenSearch**` in the Table/GSI column
- **GSI Status column**: Add a `Status` column to the GSI table showing `RETAINED` vs `REMOVED (OpenSearch)` when evolving from DDB-only to hybrid
- **OpenSearch index schema**: Document the index schema (JSON format) for each entity type indexed
- **Sync mechanism**: Document how DDB changes reach OpenSearch (Zero-ETL pipeline, DDB Streams, application-level dual-write)

See [Search-Offload-Strategy.md](./Search-Offload-Strategy.md) for detailed patterns.

### 8. SRS Design Deviations

When the Data View design intentionally deviates from an SRS requirement, document it explicitly in the Considerations table:

```markdown
| [Feature] | **[Chosen approach]** | **Design deviation from SRS**: SRS ([requirement ID]) specifies [what SRS says]. This design chooses [different approach] because [rationale]. [Migration path if applicable]. |
```

Common deviation examples:
- **Cache vs API call**: SRS says "maintain internal cache" but design chooses API-call at request time (simpler, no cache consistency)
- **Sync vs async**: SRS implies synchronous but design uses async processing (better scalability)
- **Denormalization choice**: SRS assumes data is co-located but design normalizes (different PK structure)

**Purpose**: Ensures reviewers understand deviations are intentional, not oversights. Provides traceability for future discussions.

---

## Output Format

```markdown
# Considerations

| Item | Options | Notes |
|------|---------|-------|
| [Decision topic] | **Option A** (Recommended) | [Rationale for recommendation] |
|                  | Option B | [Why this option was considered but not recommended] |
```

---

## Design Decisions Checklist

Before proceeding past the Design Decisions phase, verify all required decisions are documented:

- [ ] Single Table vs Multi-Table decision with justification
- [ ] Optimistic Locking / Versioning decision (no / selective / full)
- [ ] Global Table write consistency strategy
- [ ] Denormalization decisions for each entity relationship
- [ ] TTL usage identified for ephemeral data
- [ ] Pagination approach documented
- [ ] Search strategy decision (DynamoDB GSIs only / OpenSearch / Hybrid)
- [ ] All decisions presented to user for approval at Checkpoint #1.5
