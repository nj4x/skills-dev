# Testing Standards

When reviewing test files, validate against established testing patterns.

## Kotlin Test Framework

**Preferred over JUnit Jupiter** (note: the imports listed below are examples and not exhaustive):

```kotlin
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlin.test.expect
```

## MockK Framework

**Primary mocking framework** (not Mockito, except for simple validator tests). The imports listed below are examples and not exhaustive:

```kotlin
import io.mockk.Called
import io.mockk.CapturingSlot
import io.mockk.MockKAnnotations
import io.mockk.MockKStubScope
import io.mockk.Runs
import io.mockk.clearAllMocks
import io.mockk.clearMocks
import io.mockk.coVerify
import io.mockk.confirmVerified
import io.mockk.every
import io.mockk.impl.annotations.InjectMockKs
import io.mockk.impl.annotations.MockK
import io.mockk.impl.annotations.SpyK
import io.mockk.junit5.MockKExtension
import io.mockk.just
import io.mockk.justRun
import io.mockk.mockk
import io.mockk.mockkObject
import io.mockk.mockkStatic
import io.mockk.runs
import io.mockk.slot
import io.mockk.spyk
import io.mockk.unmockkStatic
import io.mockk.verify
import io.mockk.verifyOrder
import io.mockk.verifySequence
```

## MockK Verify Pitfall — Type Erasure

`any<SpecificType>()` inside `verify {}` does **not** check the type at runtime (generics are erased). Always use `match {}` for type-specific verification:

```kotlin
// ❌ BAD — generic is erased, passes even if called with a different Event type
verify { eventPublisher.publish(any<GroupCreatedEvent>()) }

// ✅ GOOD — explicit runtime type check
verify { eventPublisher.publish(match { it is GroupCreatedEvent }) }
```

## Test Naming Conventions

- **Backtick descriptive names**: `` `should return user when user exists` ``
- **Clear intent**: Names should describe the expected behavior
- **Given-When-Then structure** when possible

## Controller Tests

- Use `@ControllerDocumentationTest` annotation
- Use `MockMvc`, `@MockkBean`, and `TestParameters<T>` for parameterized document generation tests

### Controller Test — Full Dependency Mocking (MANDATORY — Do NOT flag as violation)

When testing a controller with `@ControllerDocumentationTest`, ALL constructor-injected dependencies
of the tested controller MUST be declared as `@MockkBean` in EVERY test class for that controller,
regardless of whether a specific test file directly invokes them.

This is required because Spring must wire the complete controller bean in the test application
context, which demands all its constructor dependencies to be present.

❌ **DO NOT flag** `@MockkBean` fields in `@ControllerDocumentationTest` classes as
"unnecessary dependencies" simply because they are not directly called in that test's scenarios.

✅ **CORRECT**: A controller with 4 use case dependencies requires 4 `@MockkBean` declarations
in each of its documentation test classes, even if only 1 is exercised per test file.

## UseCase Tests

- Unit tests with MockK mocks
- Use `@ExtendWith(MockKExtension::class)`
- Focus on business logic validation
- Test edge cases and error conditions

## Validator Tests

- Cover valid/invalid inputs with clear assertions
- Test boundary conditions
- Verify error messages and codes

## Event Tests

- Verify event exhaustiveness with `require(generatedEvents.size == allConcreteSubclasses.size)` sealed class traversal
- Test event payload correctness
- Validate event publishing timing

## DynamoDB Tests

- Use `@DdbTest` annotation for integration tests
- Test optimistic locking scenarios
- Validate query and update operations

## OpenAPI Documentation Tests

- Use `@ParameterizedTest` + `@MethodSource` generating RestDocs snippets via `epages/restdocs-api-spec`
- Validate API contract compliance
- Test request/response examples

## Test Independence

- **No shared mutable state** between tests
- Each test should be isolated
- Use `@BeforeEach` and `@AfterEach` for setup/teardown
- Avoid static state when possible

## Common Testing Patterns to Validate

### Test Structure
```kotlin
@Test
fun `should return user when user exists`() {
    // Given
    val userId = "user123"
    every { userRepository.findById(userId) } returns User(userId, "John Doe")
    
    // When
    val result = userService.getUser(userId)
    
    // Then
    assertNotNull(result)
    assertEquals(userId, result.id)
    assertEquals("John Doe", result.name)
    
    verify { userRepository.findById(userId) }
}
```

### Exception Testing
```kotlin
@Test
fun `should throw UserNotFoundException when user does not exist`() {
    // Given
    val userId = "nonexistent"
    every { userRepository.findById(userId) } returns null
    
    // When/Then
    val exception = assertFailsWith<UserNotFoundException> {
        userService.getUser(userId)
    }
    
    assertEquals("User not found: $userId", exception.message)
}
```

### Mock Verification
```kotlin
@Test
fun `should call repository to save user`() {
    // Given
    val user = User("user123", "John Doe")
    
    // When
    userService.createUser(user)
    
    // Then
    verify(exactly = 1) { userRepository.save(match { it.id == "user123" }) }
}
```

## Testing Quality Checklist

- [ ] **Test naming** is descriptive and follows conventions
- [ ] **Test independence** - no shared state between tests
- [ ] **Complete coverage** - positive, negative, and edge cases
- [ ] **Proper mocking** - using MockK correctly with type-safe verification
- [ ] **Clear assertions** - specific and meaningful
- [ ] **Setup/teardown** - proper use of @BeforeEach/@AfterEach
- [ ] **Exception handling** - testing error conditions
- [ ] **Documentation** - OpenAPI specs generated correctly
- [ ] **Framework usage** - using Kotlin Test Framework over JUnit