# Architecture Pattern Detection

This module contains Git command patterns for detecting architecture violations in code reviews, especially for large changesets.

Scope note: examples below assume committed scope and use the merge-base (three-dot) baseline `origin/$REVIEW_BASE_REF...HEAD`, where `REVIEW_BASE_REF` is the discovered PR base branch (default `main`). For working-tree scope, replace that baseline with `HEAD`. PR review consumes PR metadata and diffs without local worktree isolation.

## Priority 1: MAJOR Architecture Issues

### Field Injection Anti-Pattern
```bash
git --no-pager diff "origin/...HEAD" | grep -E "@Autowired[^{]*private"
```

### Business Logic in Controllers
```bash
git --no-pager diff "origin/...HEAD" -- '**/*Controller.kt' '**/*Controller.java' | grep -E "@Autowired.*Repository"
```

### Exposed DynamoDB Types
```bash
git --no-pager diff "origin/...HEAD" | grep -E "Map<String,\s*AttributeValue>"
git --no-pager diff "origin/...HEAD" | grep -E "return.*\.item\(\)"
```

### No Optimistic Locking
```bash
git --no-pager diff "origin/...HEAD" | grep -E "@DynamoDbBean" -A 20 | grep -v "@DynamoDbVersionAttribute" || true
```

### DynamoDB `Limit` + `FilterExpression` Misuse

DynamoDB evaluates `Limit` against *scanned* (pre-filter) items — **not** against items that match the filter. A `Query` with `.limit(1)` and a `FilterExpression` can return zero results even though matching items exist further in the partition. This causes false "nothing found" results and is a silent correctness bug.

**Detect:**
```bash
# Flag .limit(N) calls that appear near a filterExpression in the same method
git --no-pager diff "origin/...HEAD" | grep -E "\.limit\([0-9]" -A 10 | grep -E "filterExpression" || true
```

**Correct patterns for existence checks:**
- Omit `.limit()` entirely and lazily call `.flatMap { it.items() }.firstOrNull()` — the SDK fetches pages on demand and stops at the first match.
- For counting, accumulate across pages with `.sumOf { it.items().size }` (no limit).
- Prefer natural-key SK prefixes (`begins_with(SK, "A#{roleId}#")`) over `FilterExpression` when the discriminating value is encoded in the key — this narrows the scan at the storage layer.

### Missing Input Validation
```bash
git --no-pager diff "origin/...HEAD" | grep -E "@(Post|Put)Mapping" -A 3 | grep -E "@RequestBody" | grep -v "@Valid"
```

### N+1 Query Pattern
```bash
git --no-pager diff "origin/...HEAD" | grep -E "for.*\).*\{" -A 5 | grep -E "repository\.find"
```

### No Pagination
```bash
git --no-pager diff "origin/...HEAD" | grep -E "(List<.*>|return.*\.)?(getAll|findAll)(By[A-Z][a-zA-Z]*)?\("
```

---

## Priority 2: MINOR Architecture Issues

### Circular Dependencies
Check imports against the module structure defined in the project's Module View document. Look for imports crossing module boundaries in the wrong direction:
```bash
# List all changed imports to manually verify against module dependency rules
git --no-pager diff "origin/...HEAD" | grep -E "^\\+import " | sort -u
```

### Wrong Layer Access
```bash
git --no-pager diff "origin/...HEAD" | grep -E "import.*\.entity\."  # Entities imported outside repository
```

### Missing Repository Interface
```bash
git --no-pager diff "origin/...HEAD" | grep -E "new.*RepositoryImpl"  # Direct instantiation
```

### Inconsistent Naming
```bash
git --no-pager diff "origin/...HEAD" | grep -E "(class|interface) [A-Z][a-zA-Z]*Impl"  # Implementation suffix
```

---

## Architecture Pattern Priority Matrix

| Pattern | Severity | Points | Command Snippet |
|---------|----------|--------|----------------|
| Business Logic in Controllers | 🟠 MAJOR | -8 | `grep -E "@Autowired.*Repository"` |
| Exposed DynamoDB | 🟠 MAJOR | -8 | `grep -E "AttributeValue"` |
| Field Injection | 🟠 MAJOR | -8 | `grep -E "@Autowired.*private"` |
| Missing @Valid | 🟠 MAJOR | -8 | `grep -E "@RequestBody.*-v @Valid"` |
| N+1 Queries | 🟠 MAJOR | -8 | `grep -E "for.*repository\.find"` |
| No Pagination | 🟠 MAJOR | -8 | `grep -E "getAll\|findAll"` |
| DynamoDB Limit+Filter Misuse | 🟠 MAJOR | -8 | `grep -E "\.limit\(" -A 10 \| grep filterExpression` |
| Circular Dependencies | 🟡 MINOR | -3 | Check imports against Module View |
| Wrong Layer Access | 🟡 MINOR | -3 | `grep -E "import.*\.entity\."` |
| Missing Interface | 🟡 MINOR | -3 | `grep -E "new.*RepositoryImpl"` |

---

## Targeted Review Commands

### By Package

```bash
# Auth/Security Package
git --no-pager diff "origin/...HEAD" -- '**/auth/**' '**/security/**'

# Service Layer (Business Logic)
git --no-pager diff "origin/...HEAD" -- '**/*Service*.kt' '**/*Service*.java' '**/*UseCase*.kt'

# Repository/Data Access
git --no-pager diff "origin/...HEAD" -- '**/*Repository*'

# Configuration Files
git --no-pager diff "origin/...HEAD" -- '**/*.yml' '**/*.properties' '**/*Config.kt' '**/*Config.java'
```

### By Layer

```bash
# API Layer
git --no-pager diff "origin/...HEAD" -- '**/*Controller.kt' '**/*Controller.java'

# Service Layer
git --no-pager diff "origin/...HEAD" -- '**/*Service.kt' '**/*UseCase.kt' '**/*Service.java'

# Repository Layer
git --no-pager diff "origin/...HEAD" -- '**/*Repository.kt' '**/*Repository.java'
```

### Exclusion Patterns

```bash
# Exclude tests
git --no-pager diff "origin/...HEAD" -- ':!**/*Test.kt' ':!**/*Test.java' ':!**/test/**'

# Exclude test resources
git --no-pager diff "origin/...HEAD" -- ':!**/test/resources/**'

# Focus on source only
git --no-pager diff "origin/...HEAD" -- 'src/main/**'
```

---

## Context Discovery Commands

### Find Configuration Changes

```bash
# Find changed config files
git --no-pager diff "origin/...HEAD" --name-only | grep -E '\.(yml|yaml|properties|json)$'
```

### Find Entity References

```bash
# Search for entity references across codebase
git grep "Entity" -- '*.kt' '*.java' | grep -E "import.*entity"
```

### Find Method Usage

```bash
# Find method calls (example)
git grep "\.createUser(" -- '*.kt' '*.java'

# Find test references (example)
git grep "createUser" -- '*Test.kt' '*Test.java'
```

### Find Event Publishing

```bash
# Find event publishing code
git --no-pager diff "origin/...HEAD" | grep -E "(publish|emit|send.*Event|kafkaProducer\.produce|\.produce\()"
```

### Find API Changes

```bash
# Find OpenAPI/REST changes
git --no-pager diff "origin/...HEAD" | grep -E "@(GetMapping|PostMapping|PutMapping|DeleteMapping)"
```

### Find DynamoDB Changes

```bash
# Find DynamoDB entity changes
git --no-pager diff "origin/...HEAD" | grep -E "@DynamoDb(PartitionKey|SortKey|Attribute)"
```

---

## Usage Guidelines

### For Small Changesets
Use basic commands to scan the full diff for architecture patterns.

### For Medium Changesets
Focus on high-risk areas:
- Cross-module dependencies
- Layer boundary violations
- Repository implementations
- Controller complexity

### For Large Changesets
1. Start with MAJOR pattern detection
2. Then MINOR pattern detection
3. Finally targeted review by architectural concern

### Performance Tips

- **Always use `--no-pager`** to avoid interactive pagers blocking automation
- **Add `|| true`** to grep commands that may find nothing (prevents pipeline failures)
- **Use `grep -v`** (not `grep -L`) to exclude patterns from piped input
- **Add `-A` and `-B` flags** for context lines when needed (e.g., `-A 5` for 5 lines after match)
- **Keep grep patterns simple** - complex regex can be slow on large diffs
