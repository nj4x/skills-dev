# Search Offload Strategy

Patterns for offloading search, sort, and filter operations from DynamoDB to an external search engine (e.g., OpenSearch).

---

## When to Offload Search

| Signal | DynamoDB GSIs Sufficient | OpenSearch Needed |
|--------|--------------------------|-------------------|
| Search fields | 1-2 fields, prefix-only | Multiple fields, full-text, substring |
| Sort requirements | Single field per GSI | Multiple sort criteria, dynamic sorting |
| Filter complexity | Simple equality or begins_with | Boolean logic, range filters, nested conditions |
| Pagination | Tag-based cursor (DDB native) | Offset/size or search_after |
| Analytics | Not needed | Aggregations, facets, statistics |
| Fuzzy matching | Not supported | Typo-tolerant, phonetic matching |

---

## Architecture Pattern: DynamoDB + OpenSearch Hybrid

```
Write Path:
  Application → DynamoDB (source of truth)
             → OpenSearch (search index, via sync mechanism)

Read Path:
  Point lookups / GetItem    → DynamoDB (direct)
  List / Search / Sort       → OpenSearch
  Reverse lookups (GSI)      → DynamoDB (retained GSIs)
  Transactional reads        → DynamoDB
```

### Sync Mechanisms

| Mechanism | Latency | Complexity | Use When |
|-----------|---------|------------|----------|
| **Zero-ETL pipeline** | Near real-time | Low (managed) | AWS-native setup; DDB → OpenSearch automatic sync |
| **DynamoDB Streams + Lambda** | Seconds | Medium | Custom transformation needed before indexing |
| **Application dual-write** | Immediate | High | Fine-grained control; but risks inconsistency on partial failure |

**Recommendation**: Zero-ETL pipeline for most cases. Application dual-write only when custom index transformation is needed.

---

## Impact on Data View Document

### Access Patterns Summary Table

When OpenSearch handles an access pattern, mark it clearly in the Table/GSI column:

```markdown
| # | Access Pattern | API / Event | Table / Search | Operation |
|---|---------------|-------------|----------------|-----------|
| 1 | Create group | GRP-API-101 | Single Table | PutItem + OpenSearch index |
| 4 | List groups (sort by name) | GRP-API-103 | **OpenSearch** | Search with sort |
| 8 | List groups by memberUserId | GRP-API-103 | group_member_id_gsi → **OpenSearch** | Query + Search filter |
```

**Convention**: Bold `**OpenSearch**` in the column to visually distinguish from DDB operations.

### GSI Documentation with Status

When OpenSearch replaces GSIs that were previously used for search/sort, add a **Status** column:

```markdown
| GSI Name | PK | SK | Projection | Purpose | **Status** |
|----------|----|----|------------|---------|------------|
| membership_uuid_gsi | id | — | INCLUDE (pk, sk) | Resolve UUID | **RETAINED** |
| org_groups_gsi | orgId | groupBusinessId | ALL | Org-scoped lookup | **RETAINED** |
| group_name_gsi | orgId | groupNameLower | ALL | Sort by name | **REMOVED** (OpenSearch) |
| group_created_at_gsi | orgId | createdAt | ALL | Sort by date | **REMOVED** (OpenSearch) |
```

Document GSI reduction metrics (e.g., "5 → 3 GSIs, 40% reduction").

### OpenSearch Index Schema Section

Document the OpenSearch index schema for each entity type:

```markdown
# OpenSearch Integration

## Search Index Schema

### [Entity] Documents
\`\`\`json
{
  "pk": "string",
  "sk": "string",
  "entityType": "string",
  "id": "string",
  "orgId": "string",
  "name": "string",
  "description": "string",
  "createdAt": "date",
  ...
}
\`\`\`
```

### Search Capabilities Summary

Document what OpenSearch enables:

```markdown
## Search Capabilities

| Feature | OpenSearch Support | Benefits |
|---------|-------------------|----------|
| Full-text search | ✅ | Search across name, description, displayName |
| Complex filtering | ✅ | Multi-field filters, boolean logic |
| Advanced sorting | ✅ | Sort by any field, multiple criteria |
| Pagination | ✅ | Native offset/size or search_after |
| Aggregations | ✅ | Counts, statistics, facets |
```

---

## Query Pattern Notation for OpenSearch

When documenting query patterns that use OpenSearch, use this notation:

```markdown
| Use Case | Steps | Query Patterns | Notes |
|----------|-------|----------------|-------|
| Sort by name | N/A | **SEARCH OpenSearch** | Sorted by groupName ascending |
| Filter by member | 1. Get memberships | QUERY group_member_id_gsi WHERE pk={userId} | Returns groupIds |
|                   | 2. Search filter | **SEARCH OpenSearch WHERE groupId IN {groupIds}** | Application-side filter |
```

**Convention**: Use `**SEARCH OpenSearch**` prefix (bold) for OpenSearch operations, distinguishing them from DDB `QUERY`, `GET`, `PUT` operations.

---

## Retained GSIs (What OpenSearch Does NOT Replace)

Even with OpenSearch, some GSIs must be retained because they support operations that require DynamoDB's transactional consistency or reverse lookups:

| GSI Type | Why Retained | Example |
|----------|-------------|---------|
| **UUID resolver** | Point lookups for write operations (update, delete) need DDB consistency | `membership_uuid_gsi` |
| **Reverse lookup** | Cascade operations, circular reference detection, event handlers | `group_member_id_gsi` |
| **Org-scoped lookup** | Get-by-business-ID needs DDB consistency for writes | `org_groups_gsi` |

**Rule**: Retain GSIs used by write operations, event handlers, and transactional reads. Remove GSIs used only by search/list/sort read operations.
