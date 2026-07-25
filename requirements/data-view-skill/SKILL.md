---
name: data-view-skill
description: Creates Data View documents that map software requirements and API definitions to DynamoDB table designs. Use this skill when designing DynamoDB schemas, creating data view documents, mapping API operations to DynamoDB access patterns, or reviewing database designs for DynamoDB-backed microservices. This skill transforms SRS and API Definition documents into concrete DynamoDB table schemas with query patterns.---

# Data View Skill

> **⚠️ IMPORTANT**: This skill transforms SRS requirements, API definitions, and Use Case Diagrams into DynamoDB Data View documents. It REQUIRES existing SRS, API Definition, and/or Use Case Diagrams documents as input and has MANDATORY confirmation checkpoints.

This skill helps create Data View documents for DynamoDB-backed microservices by:
- Extracting entities and access patterns from SRS/API Definition documents
- Designing DynamoDB table schemas (PK/SK, attributes, types)
- Mapping every API endpoint to concrete DynamoDB query patterns
- Designing GSIs for secondary access patterns
- Documenting denormalization decisions with trade-off analysis
- Documenting CUD constraints as DynamoDB condition expressions
- Identifying design risks and open questions

---

## Workflow Summary with Checkpoints

### Phase 1: Initialization (BLOCKING)
1. **CHECKPOINT #1** - Confirm skill activation and source documents
   - Action: Confirm Data View skill usage
   - Action: Identify source SRS and API Definition documents
   - Condition: WAIT for explicit user confirmation
   - If user activated via `use_skill` → Proceed to source identification

### Phase 2: Source Analysis
2. **Step 1** - Read skill documentation files
3. **Step 2** - Load and analyze source documents (SRS, API Definition, Use Cases)
4. **Step 3** - Extract entities and their attributes
5. **Step 4** - Catalog all API endpoints and their access patterns
6. **Step 5** - Identify event handlers (consumed/produced) that need data operations

### Phase 3: Design Decisions (BLOCKING)
7. **Step 6** - Evaluate design considerations (versioning, table strategy, denormalization)
8. **CHECKPOINT #1.5** - Present design decisions for user approval

### Phase 4: Data Modeling
9. **Step 7** - Design table schemas with PK/SK patterns
10. **Step 8** - Design GSIs for secondary access patterns
11. **Step 9** - Map each API endpoint to DynamoDB query patterns
12. **Step 10** - Map event handlers to query patterns
13. **Step 11** - Document CUD constraints
14. **Step 12** - Identify points of interest and open questions

### Phase 5: Iterative Refinement Loop (BLOCKING)
15. **CHECKPOINT #2** - Present draft Data View + suggestions, wait for approval

### Phase 6: Finalization
16. **Step 13** - Write Data View document to file

### Decision Rules
| Condition | Action |
|-----------|--------|
| User has NOT confirmed at Checkpoint #1 | WAIT - Do not proceed |
| User has NOT approved design decisions at Checkpoint #1.5 | LOOP - Revise decisions |
| User has NOT approved at Checkpoint #2 | LOOP - Return to refinement |
| User says "yes", "approved", "satisfied", "proceed" | PROCEED to next phase |
| User provides feedback or says "no" | INCORPORATE changes, stay in loop |

---

## 0. Confirm Skill Activation (MANDATORY CHECKPOINT #1)

**⛔ STOP - Do not proceed without user confirmation**

Before proceeding with ANY data view work:
1. Ask the user: "I can help create a DynamoDB Data View document. Would you like me to use the Data View skill?"
2. Identify the source documents:
   - Ask: "Please provide the path(s) to the SRS, API Definition, and/or Use Case Diagrams documents"
   - OR identify from user's request if already provided
3. Confirm the target service/domain (e.g., "Group Management", "Federation")
4. **Wait for explicit user confirmation**
5. Only after receiving confirmation, proceed to Step 1

> **Note**: If user activates via `use_skill`, this checkpoint is satisfied but source document identification is still required.

---

## 1. Read Skill Documentation

Read the following documentation files to understand Data View structure and conventions:

- [Document-Structure.md](<skill dir>/docs/Document-Structure.md) - Data View document template and section ordering
- [DynamoDB-Patterns.md](<skill dir>/docs/DynamoDB-Patterns.md) - DynamoDB design patterns reference
- [Query-Pattern-Notation.md](<skill dir>/docs/Query-Pattern-Notation.md) - Query pattern notation conventions
- [Table-Design.md](<skill dir>/docs/Table-Design.md) - Table definition format and key conventions
- [Denormalization-Strategy.md](<skill dir>/docs/Denormalization-Strategy.md) - Denormalization analysis framework
- [Considerations-Template.md](<skill dir>/docs/Considerations-Template.md) - Design decisions template
- [CUD-Constraints.md](<skill dir>/docs/CUD-Constraints.md) - CUD constraint patterns
- [Search-Offload-Strategy.md](<skill dir>/docs/Search-Offload-Strategy.md) - OpenSearch search offload patterns
- [MCP-Usage.md](<skill dir>/docs/MCP-Usage.md) - MCP semantic search usage

---

## 2. Load and Analyze Source Documents

### 2.1 Source Document Access

Load source documents provided by the user:

1. Use MCP `index_files` to index source documents (if not already indexed)
2. Use MCP `search_documents` for semantic exploration
3. Parse the document structure to identify:
   - Entity definitions (from SRS Entity Reference section)
   - API endpoints (from API Definition)
   - Use case flows (from Use Case Diagrams)
   - Event definitions (from SRS Event Reference section)

### 2.2 Extract Entities

From the SRS Entity Reference section, extract:
- Entity names and their attributes
- Attribute types, constraints (required, immutable)
- Relationships between entities

### 2.3 Catalog Access Patterns

From the API Definition, catalog every endpoint:

| API ID | Method | Path | Access Type | Description |
|--------|--------|------|-------------|-------------|
| GRP-API-101 | POST | /v2/groups | Write | Create group |
| GRP-API-102 | GET | /v2/groups/{id} | Read (single) | Get group |
| ... | ... | ... | ... | ... |

Classify each pattern:
- **Read (single)**: GetItem operations
- **Read (list)**: Query/Scan operations
- **Write (create)**: PutItem operations
- **Write (update)**: UpdateItem operations
- **Write (delete)**: DeleteItem operations
- **Read+Write (complex)**: Transactional operations

### 2.4 Identify Event Handlers

From the SRS Event Reference:
- **Consumed events**: Events that trigger data operations (e.g., UserDeleted → cascade delete)
- **Produced events**: Events emitted after data operations (no direct DB impact but inform design)

---

## 3. Evaluate Design Considerations

Follow [Considerations-Template.md](<skill dir>/docs/Considerations-Template.md) to evaluate and document:

### Required Decisions
1. **Single Table vs Multi-Table** — evaluate based on access pattern overlap
2. **Optimistic Locking / Versioning** — evaluate read-before-write trade-offs
3. **Global Table Strategy** — multi-region write consistency approach
4. **Denormalization decisions** — for each entity relationship (see [Denormalization-Strategy.md](<skill dir>/docs/Denormalization-Strategy.md))
5. **TTL usage** — which entities need automatic expiration
6. **Pagination approach** — tag-based cursor implementation
7. **Search strategy** — DynamoDB GSIs only vs OpenSearch offload (see [Search-Offload-Strategy.md](<skill dir>/docs/Search-Offload-Strategy.md))

---

## CHECKPOINT #1.5: Design Decisions Approval (MANDATORY)

**⛔ STOP - Present design decisions and wait for user approval**

1. Present the design decisions table to the user
2. Ask: "Please review these design decisions. Would you like to modify any?"
3. **Wait for explicit approval** before proceeding to table design

---

## 4. Design Table Schemas

Follow [Table-Design.md](<skill dir>/docs/Table-Design.md) for:
- PK/SK pattern design driven by access patterns
- Attribute documentation with types
- GSI design and justification

Follow [DynamoDB-Patterns.md](<skill dir>/docs/DynamoDB-Patterns.md) for:
- Common DynamoDB patterns (one-to-many, many-to-many, adjacency list)
- Partition key selection criteria
- Transaction patterns

---

## 5. Map Query Patterns

Follow [Query-Pattern-Notation.md](<skill dir>/docs/Query-Pattern-Notation.md) for:
- Consistent DynamoDB operation notation
- Multi-step use case documentation
- Denormalization tracking in query patterns

For each SRS functional requirement section, map every use case to its DynamoDB operations.

> **Parallel fan-out (≥3 feature groups, advisory):** Once table schemas and GSIs are finalized (they must be — query-pattern notation references actual PK/SK values), fan out one Agent subagent per major SRS feature group **in a single message**. Each subagent maps its group's API endpoints to query patterns and writes its result to a unique temp path. Main thread reconciles: merge the mappings and run the mandatory cross-consistency check (GSI usage conflicts, overlapping patterns, unresolved access patterns) — this check requires the unified view and always stays in the main conversation. Fall back to serial mapping when fewer than 3 feature groups exist, groups share heavy context, or any subagent fails. The schema→mapping ordering is strict; never fan out before schemas are final.

---

## 6. Document CUD Constraints

Follow [CUD-Constraints.md](<skill dir>/docs/CUD-Constraints.md) for:
- Uniqueness constraints → DynamoDB condition expressions
- State guards → Condition expressions
- Referential integrity → TransactWriteItems
- Count-based constraints → Metadata items

---

## 7. Iterative Refinement Loop (MANDATORY CHECKPOINT #2)

> **⛔ CRITICAL**: MANDATORY. Do NOT write to file without user approval.

### 7.1 Present Draft and Ask for Feedback (REQUIRED)

1. **Present the draft Data View** to the user
2. **Cross-consistency verification** (MANDATORY before presenting):
   - Every query pattern in "Query Patterns" and "Event Handlers" sections must reference PK/SK values that exactly match the "Table Schema" section
   - Every query in "Points of Interest" must use the correct key patterns from the schema
   - Event handler queries must go through the correct GSI given the actual PK structure (e.g., if PK is UUID-based, org-scoped queries must use the org GSI — not query the base table by orgId)
   - If the design evolved (e.g., multi-table → single-table), verify ALL sections were updated — copy-paste from a previous approach is a common source of inconsistencies
3. **Self-analyze** for:
   - Missing access patterns (API endpoints without query patterns)
   - Hot partition risks
   - Missing GSIs for required query patterns
   - Denormalization gaps
   - Transaction size concerns (DynamoDB 100-item limit)
4. **Provide improvement suggestions**
5. **Ask**: "Would you like to make any changes to this Data View?"
6. **Wait for user response**

### 7.2 Single Refinement Mode (ALTERNATIVE)

**Trigger phrases**: "refine", "one by one", "checkpoint after each"

1. Wait for user's single refinement instruction
2. Apply ONLY the requested change
3. Present checkpoint showing the change
4. Ask: "Refinement applied. Would you like to provide another refinement, or finalize?"
5. If another refinement → Return to step 1
6. If finalize → Proceed to Section 8

### 7.3 Confirmation Checkpoint (REQUIRED)

**⛔ STOP** - Ask: **"Are you satisfied with this Data View, or would you like further refinements?"**

- **If NO**: Return to step 7.1
- **If YES**: Proceed to step 8

---

## 8. Write Data View Document to File

### 8.1 Output Location

Write to: `<Project Root>/.data/output/[Domain]-Data-View-[Version].md`

Example: `.data/output/Group-Management-Data-View-2.0.md`

### 8.2 Document Structure

Follow template in [Document-Structure.md](<skill dir>/docs/Document-Structure.md).

---

## Quick Reference

### DynamoDB Operations

| Operation | Notation |
|-----------|----------|
| Get Item | `GET [table] WHERE PK={value} AND SK={value}` |
| Put Item | `PUT [table] WHERE not_exists(PK)` |
| Update Item | `UPDATE [table] WHERE exists(PK)` |
| Delete Item | `DELETE [table] WHERE exists(PK)` |
| Query | `QUERY [table/gsi] WHERE PK={value}` |
| Scan | `SCAN [table]` (avoid) |
| Condition Check | `ConditionCheck [table] WHERE PK={value}` |
| Transaction | `Transactional Write` + numbered operations |

### Common Patterns

| Pattern | Implementation |
|---------|----------------|
| One-to-Many | PK=parentId, SK=childPrefix#childId |
| UUID Lookup | Separate lookup table: PK=uuid → returns natural keys |
| Uniqueness | PUT WHERE not_exists(PK) in transaction |
| Cascade Delete | Async via self-consumed Kafka event |
| Tag-based Pagination | Encode lastEvaluatedKey as base64 → nextPageTag |
