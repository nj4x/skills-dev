# Code Review Workflow: Compliance Reference (Steps 5–10)

Disclosed from [workflow.md](workflow.md). Step numbers match the references in workflow.md and SKILL.md.

> ⛔ **These are NOT orchestrator steps.** All effort levels analyze via subagents (Step 4.1 finders, or the Step 4.9 single subagent), never inline. This section is the **detailed compliance reference** those subagents consult. The Finder prompts point here for the parts they cannot carry inline — the framework-validation `BAD_REQUEST` allowance (Step 8.x.1), the Data View severity policy (Step 8.5.1), and the API documentation severity policy (Step 8.y). The compliance reference ends at Step 10; orchestrator steps resume at Step 10.5 (Lineage) under the divider below.

## Step 5: Validate Commit Messages

> **Scope gate**: Only applies when `--scope committed`. Skip when `--scope working-tree` (changes are uncommitted, no commit messages to validate).

Check each commit in `origin/$REVIEW_BASE_REF..HEAD` (two-dot range: commits unique to this branch) for Jira ticket reference:
- Pattern: `[A-Z]+-\d+:` at start
- **🟠 MAJOR issue** if missing

---

## Step 6: Kotlin Coding Standards

Validate code against the project's established Kotlin conventions.

**Key areas to check:**
- [ ] **Vertical Slice**: UseCases are `@Service` with `operator fun invoke()`. Controllers are thin (no business logic). Constructor injection only — no `@Autowired` on fields.
- [ ] **Three-Tier Model**: API models → Resources → Entities. Entities must NOT leak beyond `RepositoryImpl`. Repositories accept/return Resources only. Tier conversions via extension functions.
- [ ] **Request/Response models**: Request models use `@JsonIgnoreProperties(ignoreUnknown = true)`. Response models do NOT (they are serialized, not deserialized).
- [ ] **Kotlin idioms**: `data class` with `val`, extension functions for conversions, sealed interfaces for events, `checkNotNull {}` for preconditions, named constants (not magic strings).
- [ ] **Validation**: Custom validators in `validator/` sub-package, validation at API layer via `@Valid @RequestBody`. `isValid(null) = false` is **correct** for required fields — do NOT flag as dead code.
- [ ] **Error handling**: Extend base exception class, use `ErrorCode` enum, centralized `@RestControllerAdvice`. Never expose stack traces.
- [ ] **Events**: Sealed `Event` hierarchy, critical vs non-critical distinction, Kafka headers, exhaustiveness enforced in tests.
- [ ] **DynamoDB**: AWS SDK v2 Enhanced Client, no `AttributeValue` leaking outside repository, `@DynamoDbVersionAttribute` for optimistic locking.

→ See [kotlin-standards.md](kotlin-standards.md) for full standards, examples, and anti-patterns.

#### Python Projects (`PROJECT_TYPE = Python`)

> This is a per-language addendum to the inline (effort=low) review path. It does **not** replace the Kotlin/JVM guidance above — apply it only when `PROJECT_TYPE = Python`.

When reviewing Python code, apply standards from [python-standards.md](python-standards.md):

**Pydantic & Type Annotations**
- All validators use `@field_validator`/`@model_validator` (pydantic v2) — flag any legacy `@validator`/`@root_validator`
- `from typing import List/Dict/Optional/Iterator` → flag as deprecated; require `collections.abc` / built-ins
- Missing `__all__` on public `__init__.py` modules → flag as MINOR
- `TYPE_CHECKING` import pattern for type-only cross-module refs — verify it is used where needed

**DRY & Code Quality**
- Three or more near-identical code blocks → flag as MINOR with suggested abstraction
- Repeated audit-detail dicts with same base keys → flag, suggest `_build_audit` helper
- Inline `str.partition(":")` typed-id parsing → flag if `parse_typed_id` helper exists in `schemas/`
- `str(exc)` / raw exception text in audit records or user-visible output → flag as MINOR (m-2 pattern)

**SQL / DB**
- f-string or `%`-format SQL with variable identifiers → flag as MAJOR (psycopg2.sql.Identifier required)
- All values must be parameterized (`%s`) → any string-interpolated value is CRITICAL

**Testing**
- `except Exception: pass` or `except Exception as e: pass` (unused binding) in conftest teardown → flag as MINOR
- Non-parametrized near-duplicate test bodies → flag as MINOR
- `from typing import Iterator` in test fixtures → flag as MINOR

---

## Step 7: Module Architecture & Boundaries

> **PREREQUISITE**: This step requires `PROJECT_MODULE_VIEW`.
> **IF `PROJECT_MODULE_VIEW` is EMPTY**: Skip this entire step. Add to the report: "⚠️ Module View document not found — module boundary validation was skipped."

**IF `PROJECT_MODULE_VIEW` is set**: Read the file at `PROJECT_MODULE_VIEW` and validate changes against the module architecture defined in it.

**Essential rules to check (adapt based on what the Module View document defines):**
- **Zero circular dependencies** — modules depend downward only
- **Module boundaries** are respected as defined in the Module View
- **Shared modules** (e.g., `common/`) have no dependencies on feature modules
- **Dependency modules** (e.g., `dependencies/`) contain external API clients only
- **Cross-module reads** go through interfaces, not direct module access
- **Event consumers** use dependency inversion — handlers depend on interfaces, not on feature modules
- **One-way dependencies only** as specified in the Module View dependency matrix

---

## Step 8: API Definition Compliance

> **PREREQUISITE**: This step requires `PROJECT_API_DEFINITION`.
> **IF `PROJECT_API_DEFINITION` is EMPTY**: Skip the specification validation parts of this step. Add to the report: "⚠️ API Definition document not found — API specification validation was skipped."

**IF `PROJECT_API_DEFINITION` is set**: When changes touch Controllers, API models (request/response DTOs), path constants, or error codes — read the file at `PROJECT_API_DEFINITION` and validate against it.

**What to check:**
- HTTP method + path matches the specification
- Request/response field names, types, optionality, and constraints match
- Error codes and HTTP status codes are correct (with framework-validation allowance below)
- Pagination follows the project's established pattern
- Path parameter semantics are correct
- Gateway-injected headers are used correctly
- API category paths are respected (e.g., `/internal/` for service-to-service, `/v2/` for admin, `/v2/me/` for self-service)
- OpenAPI documentation annotations are present and accurate
- **Generated API specifications are present and include new endpoints**
  - Look for generated spec files (e.g., `build/api-spec/openapi3.yaml` or similar)
  - **CRITICAL**: API specifications MUST be present and MUST contain all APIs under development
  - **IF `BUILD_STATUS = SUCCESS`** and spec files are still missing or incomplete → this is a **🔴 CRITICAL** violation (the build ran but specs were not generated properly)
  - **IF `BUILD_STATUS = WAIVED`** and spec files are missing → note in the report: "⚠️ API specs not found and build/OpenAPI gate was waived in Step 2 — re-run the review with a build to validate API specifications"
  - **CRITICAL**: If new endpoints are missing from specifications, this is a critical violation
- **API documentation quality parity (consistent or better) vs API Definition**
  - Method documentation (summary/description/comments) must be semantically consistent with API Definition documentation
  - Payload documentation for request/response fields must preserve API Definition meaning (intent, constraints, required/optional semantics)
  - More detailed documentation is allowed and encouraged, as long as it does not contradict the API Definition
  - Missing key meaning/constraint from API Definition in implementation docs is considered a quality defect

### 8.x API Documentation Consistency Validation (MANDATORY when API changed)

For each changed endpoint, compare API documentation sources (generated OpenAPI descriptions and/or API documentation snippets in code/tests) against `PROJECT_API_DEFINITION`:

1. Method-level text quality:
   - HTTP method/path context is documented correctly
   - Summary and description are equivalent or better than API Definition text
2. Payload text quality:
   - Request field descriptions preserve API Definition semantics and constraints
   - Response field descriptions preserve semantics and do not weaken meaning
3. Error documentation quality:
   - Error code descriptions/status semantics are consistent with API Definition

### 8.x.1 Framework/Native Validation Allowance (IMPORTANT)

When an error is produced by native Kotlin/Spring/Jackson/Bean Validation behavior (not domain business logic),
it is acceptable for documentation/spec examples to use generic `BAD_REQUEST` semantics.

Treat as **PASS (no mismatch)** when ALL of the following are true:
- Failure source is framework/native validation (e.g., Kotlin nullability binding failure, enum parsing failure,
  `@Valid`/`@NotBlank`/`@Size`/other annotation-based validation failure, malformed request body/path/query parameter format)
- There is no custom domain error-mapping logic in the changed implementation for that case
- HTTP status semantics remain correct (typically 400)

Treat as **FAIL (mismatch)** when ANY of the following are true:
- API Definition requires a domain-specific error code for a business-rule failure handled in service/use-case logic
- Implementation documentation weakens or replaces a domain-specific business error with generic `BAD_REQUEST`
- Documentation contradicts API Definition error semantics

Examples:
- ✅ Acceptable generic `BAD_REQUEST`: invalid enum value rejected by framework binding
- ✅ Acceptable generic `BAD_REQUEST`: `@Size(min=1)` violation on request field
- ❌ Not acceptable generic `BAD_REQUEST`: documented domain case like `TEACHER_GROUP_IMMUTABLE` or
  `MEMBER_LIMIT_EXCEEDED` when that rule is business logic and explicitly defined in API Definition

**Acceptance rule: "consistent or better"**
- PASS: Equivalent meaning OR richer detail with no contradiction
- PASS: Generic `BAD_REQUEST` is allowed for framework/native validation-originated failures (per 8.x.1)
- FAIL: Contradiction, omission of key semantics/constraints, or weaker/misleading text

### 8.y Severity Policy for API Documentation Mismatches

- 🔴 **Critical**: Documentation contradicts API Definition semantics (method behavior, payload meaning, or error behavior)
- 🟠 **Major**: Key API Definition semantics/constraints are missing or significantly weaker in implementation docs
- 🟡 **Minor**: Wording/style clarity issues without semantic mismatch
- ℹ️ **No Issue**: Generic `BAD_REQUEST` used for framework/native validation-originated failures (allowed by 8.x.1)
- 🟢 **Positive**: Documentation is more detailed than API Definition while remaining fully consistent

---

## Step 8.5: Data View Compliance (DynamoDB Data Model & Access Patterns)

> **PREREQUISITE**: This step requires `PROJECT_DATA_VIEW`.
> **IF `PROJECT_DATA_VIEW` is EMPTY**: Skip this entire step. Add to the report: "⚠️ Data View document not found — data model and access pattern validation was skipped."

> **Applies when** changes touch any of the following:
> - DynamoDB entities (`@DynamoDbBean`-annotated classes)
> - Repository implementations (e.g. `*RepositoryImpl.kt`, `ddb/` sub-packages)
> - DDB constants (table name, GSI names, attribute names, key prefixes/suffixes)
> - `DynamoDbConfig` / local DDB scaffolding (`LocalDynamoDbConfig`, synthetic key entities used for local table creation)
> - Query/update expressions or new access paths

**IF `PROJECT_DATA_VIEW` is set**: Read the file at `PROJECT_DATA_VIEW` and validate the change against the documented data model and access patterns.

**What to check:**

1. **Table strategy & name**
   - Single-table vs multi-table strategy is respected as defined in the Data View
   - Canonical table name constant matches Data View (e.g., `GROUP_MGMT_TABLE_NAME = "group_mgmt"`)
   - Environment prefix/postfix composition is applied through a single canonical bean (not duplicated in multiple places)

2. **Primary keys (PK/SK)**
   - Partition key and sort key prefixes match Data View conventions (e.g. `G#`, `M#U#`, `M#G#`, `TI#`, `GN#`)
   - Key composition formulas match (e.g., `memberIdKey = "M#{memberId}#{memberType}"`)
   - Polymorphic sort key prefixes do not collide across entity types (e.g. `GN#` for groups vs `TI#` for task items)
   - Key attribute names use the constants defined in the project (no magic strings)

3. **GSIs (Global Secondary Indexes)**
   - GSI count matches Data View (e.g. Data View says 5 GSIs → code/local scaffolding must have 5)
   - For each GSI: PK attribute, SK attribute, and projection type match Data View
   - GSI names match the canonical constants
   - Synthetic "all-GSI" entities used for local table creation (e.g. `KeyEntity` in `LocalDynamoDbConfig`) expose EVERY GSI listed in Data View — a missing GSI causes local-dev tests that exercise that access path to silently fall back to scans or fail

4. **Attributes**
   - Attribute names match Data View (use constants from `DdbConstant` or equivalent)
   - Required attributes (per Data View schema rows) are non-nullable in the entity type; optional attributes are nullable
   - Denormalized fields (e.g. `parentId`, `memberNameLower`, `parentSortKey`) are populated on writes as specified
   - TTL-bearing items (e.g. task items) use `Expirable`/`@DynamoDbConvertedBy(InstantToNumberConverter)` and set the correct attribute

5. **Access patterns**
   - New or changed repository method maps to an access pattern documented in the Data View "Access Patterns Summary" table
   - The query strategy chosen (Query vs GetItem vs Scan) matches the documented strategy
   - If a new access pattern is introduced that is NOT in the Data View, flag it and ask whether the Data View document should be updated first

6. **Transactional semantics**
   - TransactWrite / BatchWrite operations match the atomicity boundaries described in Data View
   - Optimistic locking (`@DynamoDbVersionAttribute`) is used for items that the Data View marks with a `version` attribute
   - Conditional expressions for uniqueness (e.g. `attribute_not_exists(PK)` on GroupKey marker creation) are preserved

### 8.5.1 Severity Policy for Data View Mismatches

- 🔴 **Critical**: Data model change that breaks an access pattern, corrupts key-space (PK/SK prefix collision), or silently drops a GSI relied on by production access paths
- 🟠 **Major**: Attribute/GSI/Access-pattern mismatch vs Data View; magic strings used instead of canonical constants; denormalized field not populated on write; local-dev scaffolding missing a GSI that Data View lists
- 🟡 **Minor**: Naming drift from Data View (e.g. constant present but unused), comment/documentation drift, stylistic inconsistency
- 🟢 **Positive**: Change reduces duplication (single canonical table-name / key-composition bean), adds a GSI that Data View already requires, introduces missing `Auditable`/`Expirable` traits where Data View mandates them

### 8.5.2 Pre-existing vs in-scope findings

When a Data View gap is discovered (e.g., a GSI missing from a synthetic `KeyEntity`) but the reviewed diff does NOT touch the relevant code, report the gap as a **contextual observation out of scope**, not as a finding on this review. Still include it under a `📊 Data View Observations (out of scope)` bullet list in the report so it is not lost.

---

## Step 9: Business Logic & SRS Validation

> **PREREQUISITE**: This step requires `PROJECT_SRS` and optionally `PROJECT_USE_CASES`.
> **IF both `PROJECT_SRS` and `PROJECT_USE_CASES` are EMPTY**: Skip this entire step. Add to the report: "⚠️ SRS and Use Case documents not found — business logic validation was skipped."
> **IF `PROJECT_SRS` is EMPTY but `PROJECT_USE_CASES` is set** (or vice versa): Perform partial validation using whichever document is available. Note the missing document in the report.

**IF `PROJECT_SRS` is set**: When changes touch UseCase classes, validators, event handlers, or repository logic — read the file at `PROJECT_SRS` and validate against its functional requirements.

**IF `PROJECT_USE_CASES` is set**: Also read the file at `PROJECT_USE_CASES` and cross-reference use case specifications.

**What to check:**
- Business rules from the SRS are correctly enforced in use case implementations
- Authorization checks follow the permission matrix defined in the SRS
- State transitions and immutability rules are respected
- Nesting/hierarchy validation rules are implemented (circular reference prevention, etc.)
- Events are published on the correct topics with correct payloads after successful operations
- Consumed events trigger correct cascade behavior
- Error conditions from the SRS error code reference are handled with the correct error codes
- Read full method context — not just diff lines — to understand complete business flow

**Apply 2x severity multiplier** for business logic violations in UseCase classes.

---

## Step 10: Testing Standards

When reviewing test files, validate against established testing patterns.

**Key areas to check:**
- [ ] **Frameworks**: Kotlin Test Framework preferred over JUnit Jupiter. MockK is the primary mocking library (not Mockito, except for simple validator tests).
- [ ] **MockK type erasure pitfall**: Use `match { it is SpecificType }` instead of `any<SpecificType>()` inside `verify {}` — generics are erased at runtime.
- [ ] **Test naming**: Backtick descriptive names (`` `should return X when Y` ``).
- [ ] **Test types**: Controllers → `@ControllerDocumentationTest` + MockMvc. UseCases → `@ExtendWith(MockKExtension::class)`. DynamoDB → `@DdbTest`.
- [ ] **Event tests**: Sealed class exhaustiveness with `require(generatedEvents.size == allConcreteSubclasses.size)`.
- [ ] **Test independence**: No shared mutable state between tests.

> ⚠️ **Anti-false-positive — Controller Test Full Dependency Mocking**: In `@ControllerDocumentationTest` classes, `@MockkBean` declarations for controller dependencies that are **not directly invoked** in that test's scenarios are **NOT** a violation. They are mandatory for Spring application context wiring of the full controller dependency graph. Do **NOT** report these as "unnecessary dependencies" or flag them as a quality issue.

→ See [testing-standards.md](testing-standards.md) for full patterns, import lists, and code examples.
