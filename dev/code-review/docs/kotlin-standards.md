# Kotlin Coding Standards

Validate code against the project's established Kotlin conventions.

## Architecture — Vertical Slice Pattern

- **UseCase classes**: Each use case is a `@Service` class with `operator fun invoke()`. Use cases are the unit of business logic.
- **Controllers**: Thin HTTP routing only — dispatch to use cases. No business logic in controllers.
- **Repository interfaces**: Defined in `common/` as ports. Implementations live in the owning module.
- **Constructor injection**: Via Kotlin primary constructors. No `@Autowired` on fields.

```kotlin
// Good — Controller dispatches to use case
@RestController
class GroupController(
    private val useCase: CreateGroupUseCase
) {
    @PostMapping
    fun createResource(...): ResponseEntity<GroupResponse> {
        val group = useCase(command = ..., userId = ..., organizationId = ...)
        return ResponseEntity(group.asGroupResponse(), HttpStatus.CREATED)
    }
}

// Good — UseCase with operator invoke
@Service
class CreateGroupUseCase {
    operator fun invoke(command: CreateGroupCommand, userId: String, organizationId: String): Group { ... }
}
```

## Three-Tier Model Layering

Each feature module follows a three-tier model convention:

| Tier | Purpose | Location | Examples |
|------|---------|----------|----------|
| **API Models** | Request/Response DTOs with validation annotations | Feature package (`api/` sub-package) | `CreateGroupRequest`, `GroupResponse` |
| **Resources** | Business models — clean domain identity | `common/resource/` for shared; feature package for local | `Group`, `GroupMembership` |
| **Entities** | DDB persistence models — `@DynamoDbBean`, key mapping | Private to `RepositoryImpl` | `GroupEntity`, `MembershipEntity` |

**Key rules to enforce:**
- Repository interfaces in `common/` accept and return **Resources** — never Entities
- Entities are encapsulated inside `RepositoryImpl` — they must **not leak** beyond the persistence boundary
- Conversion between tiers via explicit extension functions (e.g., `asGroupResponse()`, `asCreateGroupCommand()`, `asGroupEntity()`)
- **Request models** use `@JsonIgnoreProperties(ignoreUnknown = true)` (deserialization safety) and `@JsonInclude` as needed, plus validation annotations (`@Valid`, `@field:ValidGroupId`)
- **Response models** do NOT use `@JsonIgnoreProperties` — they are serialized (not deserialized), so ignoring unknown properties is not applicable

## Kotlin Idioms

- **File naming**: Kotlin allows multiple classes per file and does not require the filename to match the class name. Grouping closely related classes in one file (e.g. a sealed hierarchy, a data class with its companion value class) is idiomatic — do not flag this as a violation. Only flag naming that is genuinely confusing or inconsistent with the surrounding codebase convention.
- **Immutable data**: `data class` with `val` properties for DTOs, Resources, Commands
- **Extension functions** for model conversion (not static mapper classes)
- **Sealed interfaces** for event hierarchies
- **`inline val` logger extensions**: Use project-specific log extensions (e.g., `commonLog`, `errorLog`, `accessLog`) — never `System.out.println` or `printStackTrace`
- **Null safety**: Leverage Kotlin's type system (`String?` vs `String`). Use `checkNotNull {}` for preconditions, not manual null checks returning null
- **DSL usage**: If the project uses custom DSLs (e.g., `ddbUpdate {}`, `FunctionChainDsl`, `StringDSL`), new code should leverage existing DSLs where applicable
- **No magic strings**: Use named constants from the project's `constants/` package (e.g., `PathConstants`, `HttpHeaders`, `MessageConstants`, `DdbConstant`)
- **Boolean naming**: Prefix with `is`, `has`, `can`, `should` (e.g., `isRoleAssignable`, `isSystemGroup`)

## Validation Pattern

- Custom constraint annotations in `validator/` sub-package per module (e.g., `@ValidGroupId`, `@ValidGroupName`, `@ValidDescription`)
- Validators implement `ConstraintValidator<A, String>` with clear, sequential validation logic
- Validation happens at API layer via `@Valid @RequestBody` — not in use cases
- **Null handling in validators**:
  - `isValid(null)` returning `false` is **CORRECT** when the validated field is a **required attribute** — do NOT flag this as dead code or suggest changing it to `return true`
  - `isValid(null)` returning `true` is only correct for **optional attributes** where null means "not provided" and should pass validation
  - Jakarta Bean Validation does not automatically skip custom validators for null values (unlike `@NotNull`) — explicitly returning `false` for null on a required field is intentional and correct

### Spring Framework 6.1+ Native Method Validation (Spring Boot 3.x)

- **`@Validated` is NOT required on controllers** for `@RequestParam` / `@PathVariable` constraint enforcement
  (`@Min`, `@Max`, `@NotBlank`, etc.). Spring Framework 6.1+ enables native handler method validation automatically
  when `spring-boot-starter-validation` is on the classpath.
- Constraint violations on handler method parameters throw `HandlerMethodValidationException` (not `ConstraintViolationException`).
  The project's `ExceptionAdvice` already handles this via `@ExceptionHandler(HandlerMethodValidationException::class)`.
- **Do NOT flag missing `@Validated` on `@RestController` classes as a defect** — it is intentionally absent in this project.
- `@Valid` on `@RequestBody` parameters remains the correct way to trigger deep bean validation on request bodies.

## Error Handling

- Custom exceptions extend the project's base exception class (e.g., `BaseGroupManagementException(errorCode: ErrorCode, errorMessage: String?)`)
- `ErrorCode` enum maps to HTTP status, code string, and default message
- `@RestControllerAdvice` handles all exception-to-response mapping centrally
- Error response structure: `{ error: { code, message } }`
- Never expose stack traces or internal details to clients

## Event Publishing

- Events implement sealed `Event` interface hierarchy
- Distinguish between critical events (synchronous, delivery ensured) and non-critical events (async, failure logged but not propagated)
- Kafka events include event type headers
- Event exhaustiveness enforced in tests via sealed class traversal (e.g., `require(generatedEvents.size == allConcreteSubclasses.size)`)

## DynamoDB Patterns

- Use AWS SDK v2 Enhanced Client API (not legacy DocumentClient)
- Never expose `AttributeValue` or DynamoDB-specific types outside repository layer
- Use project's DDB DSL for transactional operations with retry and conflict handling
- `@DynamoDbVersionAttribute` for optimistic locking
- **Data model must match the project's Data View document**: table name, PK/SK prefixes, GSI PK/SK attributes, attribute names, and TTL semantics must align with `PROJECT_DATA_VIEW`. Use the `constants/` package (e.g., `DdbConstant.GROUP_MGMT_TABLE_NAME`, `GSI_ID`, `PREFIX_GROUP`) — no magic strings for table/GSI/attribute names.
- **Access patterns must map to the Data View access-pattern table**: a new repository query/update should correspond to a documented access pattern. If it does not, flag it and ask whether Data View should be updated first.

See [workflow.md §Step 8.5](workflow.md) for the full Data View compliance check.
