# Test Case Format Guide

This document provides rules and patterns for generating test cases from SRS requirements, including ID encoding conventions and standard test case structures.

## Test Case ID Encoding

### Format

```
[SRS-Requirement-ID]-[Type]-[Number]
```

### Components

| Component | Description | Example |
|-----------|-------------|---------|
| SRS-Requirement-ID | The SRS requirement being tested | SAB-ROLE-FR-1.0.0 |
| Type | Test type indicator | P, N, E, S |
| Number | Sequential number (3 digits) | 001, 002, 003 |

### Type Indicators

| Type | Code | Description | Focus |
|------|------|-------------|-------|
| **Positive** | P | Happy path tests | Valid inputs, successful operations |
| **Negative** | N | Error handling tests | Invalid inputs, failure scenarios |
| **Edge** | E | Boundary tests | Limits, edge cases |
| **Security** | S | Security tests | Authorization, authentication |

### Examples

```
[SAB-ROLE-FR-1.0.0]-P-001  → First positive test for Create System Role
[SAB-ROLE-FR-1.0.0]-N-001  → First negative test (missing fields)
[SAB-ROLE-FR-1.0.0]-N-002  → Second negative test (data store failure)
[SAB-ROLE-FR-1.0.0]-E-001  → First edge case test
[SAB-ROLE-FR-1.0.0]-S-001  → First security test
```

---

## Test Case Structure

### Standard Format

```markdown
**Test Cases:**

1. [SRS-ID]-P-001
   - Given [precondition 1]
   - Given [precondition 2] (if needed)
   - [HTTP Method] `[Endpoint]` API call must return a `[Status Code]` status with [expected response description]

2. [SRS-ID]-N-001
   - Given [failure condition]
   - [HTTP Method] `[Endpoint]` API call must return a `[Error Status]` status with an `error.code: [ERROR_CODE]`
```

### Given-When-Then Mapping

| Component | Maps To | Example |
|-----------|---------|---------|
| **Given** | Precondition/Setup | "Given an existing system role with ID `roleId`" |
| **When** | HTTP Method + Endpoint | "POST `/internal/system-roles`" |
| **Then** | Status + Response | "must return a `201 Created` status with..." |

---

## Standard Test Categories by Operation

### Create Operation Tests

| Test ID Pattern | Type | Test Description |
|-----------------|------|------------------|
| `[ID]-P-001` | Positive | Successful creation with all valid inputs |
| `[ID]-P-002` | Positive | Successful creation with optional fields omitted |
| `[ID]-N-001` | Negative | Missing required fields |
| `[ID]-N-002` | Negative | Invalid field values/types |
| `[ID]-N-003` | Negative | Data store failure |
| `[ID]-E-001` | Edge | Maximum field length values |
| `[ID]-E-002` | Edge | Minimum field length values |
| `[ID]-S-001` | Security | Unauthorized user attempt |

**Template:**
```markdown
1. [SRS-ID]-P-001
   - Given a request body with valid `fieldA`, `fieldB`, and `fieldC`
   - POST `[endpoint]` API call must return a `201 Created` status with response body containing the created [entity] details including a unique `entityId` and `version: 1`

2. [SRS-ID]-N-001
   - Given the request body is missing required fields (e.g., `fieldA` or `fieldB`)
   - POST `[endpoint]` API call must return a `400 Bad Request` status with an `error.code: BAD_REQUEST`

3. [SRS-ID]-N-002
   - Given the system is unable to store the [entity] due to a data store failure
   - POST `[endpoint]` API call must return a `500 Internal Server Error` status with an `error.code: INTERNAL_SERVER_ERROR`
```

### Read (Single) Operation Tests

| Test ID Pattern | Type | Test Description |
|-----------------|------|------------------|
| `[ID]-P-001` | Positive | Successful retrieval of existing resource |
| `[ID]-N-001` | Negative | Resource not found |
| `[ID]-N-002` | Negative | Data store failure |
| `[ID]-S-001` | Security | Access to resource outside scope |

**Template:**
```markdown
1. [SRS-ID]-P-001
   - Given an existing [entity] with ID `entityId`
   - GET `[endpoint]/{entityId}` API call must return a `200 OK` status with a response body containing the complete [entity] details including `entityId`, `field1`, `field2`, and `version`

2. [SRS-ID]-N-001
   - Given the `entityId` does not exist in the system
   - GET `[endpoint]/{entityId}` API call must return a `404 Not Found` status with an `error.code: [ENTITY]_NOT_FOUND`

3. [SRS-ID]-N-002
   - Given the system is unable to retrieve the [entity] due to a data store failure
   - GET `[endpoint]/{entityId}` API call must return a `500 Internal Server Error` status with an `error.code: INTERNAL_SERVER_ERROR`
```

### Read (List) Operation Tests

| Test ID Pattern | Type | Test Description |
|-----------------|------|------------------|
| `[ID]-P-001` | Positive | Successful list retrieval |
| `[ID]-P-002` | Positive | Successful search with matching results |
| `[ID]-P-003` | Positive | Successful sort by valid field |
| `[ID]-N-001` | Negative | Invalid sort field |
| `[ID]-N-002` | Negative | Invalid filter parameter |
| `[ID]-N-003` | Negative | Data store failure |
| `[ID]-E-001` | Edge | Empty result set |
| `[ID]-E-002` | Edge | Maximum page size |

**Template:**
```markdown
1. [SRS-ID]-P-001
   - GET `[endpoint]` API call must return a `200 OK` status with a response body containing an `items` array listing all [entities] with `entityId`, `field1`, `field2`, and `count`

2. [SRS-ID]-P-002
   - Given a `search` query parameter with a `fieldName` or `entityId`
   - GET `[endpoint]?search={searchTerm}` API call must return a `200 OK` status with an `items` array containing only [entities] matching the search criteria

3. [SRS-ID]-P-003
   - Given `sortBy` query parameter with value `fieldName`
   - GET `[endpoint]?sortBy=fieldName` API call must return a `200 OK` status with an `items` array sorted by field name in ascending order

4. [SRS-ID]-N-001
   - Given an invalid `sortBy` parameter is used
   - GET `[endpoint]?sortBy=invalidField` API call must return a `400 Bad Request` status with an `error.code: INVALID_SORT_FIELD`

5. [SRS-ID]-N-002
   - Given the system is unable to retrieve the [entities] due to a data store failure
   - GET `[endpoint]` API call must return a `500 Internal Server Error` status with an `error.code: INTERNAL_SERVER_ERROR`
```

### Update Operation Tests

| Test ID Pattern | Type | Test Description |
|-----------------|------|------------------|
| `[ID]-P-001` | Positive | Successful update of mutable fields |
| `[ID]-P-002` | Positive | Successful partial update (some fields only) |
| `[ID]-N-001` | Negative | Resource not found |
| `[ID]-N-002` | Negative | Attempt to modify immutable field |
| `[ID]-N-003` | Negative | Data store failure |
| `[ID]-S-001` | Security | Update resource outside scope |

**Template:**
```markdown
1. [SRS-ID]-P-001
   - Given an existing [entity] with ID `entityId`
   - Given a request body with updated `field1` and `field2`
   - PATCH `[endpoint]/{entityId}` API call must return a `200 OK` status with the updated [entity] details and incremented `version`

2. [SRS-ID]-P-002
   - Given an existing [entity] with ID `entityId`
   - Given a request body with `listField` containing added and removed items
   - PATCH `[endpoint]/{entityId}` API call must return a `200 OK` status with the updated list and incremented `version`

3. [SRS-ID]-N-001
   - Given the `entityId` does not exist in the system
   - PATCH `[endpoint]/{entityId}` API call must return a `404 Not Found` status with an `error.code: [ENTITY]_NOT_FOUND`

4. [SRS-ID]-N-002
   - Given an existing [entity] with ID `entityId`
   - Given a request body attempting to update the `immutableField`
   - PATCH `[endpoint]/{entityId}` API call must return a `400 Bad Request` status with an `error.code: [FIELD]_IMMUTABLE`

5. [SRS-ID]-N-003
   - Given an existing [entity] with ID `entityId`
   - Given the system is unable to update the [entity] due to a data store failure
   - PATCH `[endpoint]/{entityId}` API call must return a `500 Internal Server Error` status with an `error.code: INTERNAL_SERVER_ERROR`
```

### Delete Operation Tests

| Test ID Pattern | Type | Test Description |
|-----------------|------|------------------|
| `[ID]-P-001` | Positive | Successful deletion with confirmation |
| `[ID]-N-001` | Negative | Resource not found |
| `[ID]-N-002` | Negative | Has active dependencies |
| `[ID]-N-003` | Negative | Missing confirmation |
| `[ID]-N-004` | Negative | Data store failure |
| `[ID]-S-001` | Security | Delete resource outside scope |

**Template:**
```markdown
1. [SRS-ID]-P-001
   - Given an existing [entity] with ID `entityId` that has no active [dependencies]
   - Given a `confirm: true` parameter
   - DELETE `[endpoint]/{entityId}?confirm=true` API call must return a `204 No Content` status and the [entity] should be permanently deleted

2. [SRS-ID]-N-001
   - Given the `entityId` does not exist in the system
   - DELETE `[endpoint]/{entityId}` API call must return a `404 Not Found` status with an `error.code: [ENTITY]_NOT_FOUND`

3. [SRS-ID]-N-002
   - Given an existing [entity] with ID `entityId` that has active [dependencies]
   - DELETE `[endpoint]/{entityId}` API call must return a `409 Conflict` status with an `error.code: [ENTITY]_HAS_ACTIVE_[DEPENDENCIES]`

4. [SRS-ID]-N-003
   - Given an existing [entity] with ID `entityId`
   - Given the `confirm` parameter is missing or set to `false`
   - DELETE `[endpoint]/{entityId}` API call must return a `400 Bad Request` status with an `error.code: CONFIRMATION_REQUIRED`

5. [SRS-ID]-N-004
   - Given an existing [entity] with ID `entityId` that has no active [dependencies]
   - Given the system is unable to delete the [entity] due to a data store failure
   - DELETE `[endpoint]/{entityId}?confirm=true` API call must return a `500 Internal Server Error` status with an `error.code: INTERNAL_SERVER_ERROR`
```

---

## Authorization Test Patterns

### Scope-Based Access

```markdown
[SRS-ID]-S-001
- Given an existing [entity] with ID `entityId` but outside their organization scope
- [METHOD] `[endpoint]/{entityId}` API call must return a `403 Forbidden` status with an `error.code: [ENTITY]_OUT_OF_SCOPE`
```

### Role-Based Access

```markdown
[SRS-ID]-S-002
- Given a user without [required role] attempts to [operation]
- [METHOD] `[endpoint]` API call must return a `403 Forbidden` status with an `error.code: FORBIDDEN`
```

### Resource Visibility

```markdown
[SRS-ID]-S-003
- Given an existing [entity] with ID `entityId` that is not applicable to their scope or assigned to them
- GET `[endpoint]/{entityId}` API call must return a `403 Forbidden` status with an `error.code: [ENTITY]_NOT_ACCESSIBLE`
```

---

## Edge Case Test Patterns

### Field Length Boundaries

```markdown
[SRS-ID]-E-001
- Given a `fieldName` with exactly [MAX_LENGTH] characters
- POST `[endpoint]` API call must return a `201 Created` status (boundary accepted)

[SRS-ID]-E-002
- Given a `fieldName` with [MAX_LENGTH + 1] characters
- POST `[endpoint]` API call must return a `400 Bad Request` status with an `error.code: FIELD_TOO_LONG`
```

### Empty Collections

```markdown
[SRS-ID]-E-003
- Given no [entities] exist matching the search criteria
- GET `[endpoint]?search={noMatchTerm}` API call must return a `200 OK` status with an empty `items` array
```

### Pagination Boundaries

```markdown
[SRS-ID]-E-004
- Given `page` parameter exceeds total pages
- GET `[endpoint]?page=9999` API call must return a `200 OK` status with an empty `items` array
```

---

## Test Case Documentation Format

### Summary Table

```markdown
## Test Case Summary

| SRS ID | Total | P | N | E | S |
|--------|-------|---|---|---|---|
| SAB-ROLE-FR-1.0.0 | 5 | 1 | 3 | 0 | 1 |
| SAB-ROLE-FR-1.0.1 | 8 | 2 | 5 | 0 | 1 |
| SAB-ROLE-FR-1.0.2 | 7 | 1 | 5 | 0 | 1 |
| **Total** | **20** | **4** | **13** | **0** | **3** |
```

### Coverage Matrix

```markdown
## Test Coverage Matrix

| Scenario | Create | Read | Update | Delete | List |
|----------|--------|------|--------|--------|------|
| Happy path | ✓ P-001 | ✓ P-001 | ✓ P-001 | ✓ P-001 | ✓ P-001 |
| Not found | - | ✓ N-001 | ✓ N-001 | ✓ N-001 | - |
| Invalid input | ✓ N-001 | - | ✓ N-002 | ✓ N-003 | ✓ N-001 |
| Data error | ✓ N-002 | ✓ N-002 | ✓ N-003 | ✓ N-004 | ✓ N-002 |
| Auth failure | ✓ S-001 | ✓ S-001 | ✓ S-001 | ✓ S-001 | ✓ S-001 |
```

---

## Deriving Tests from FS Requirements

### From FS Error Conditions

**FS Pattern:**
```
"If [condition], then the system shall [reject/error action]"
```

**Derived Test:**
```markdown
[SRS-ID]-N-XXX
- Given [condition from FS]
- [METHOD] `[endpoint]` API call must return a `[appropriate error status]` status with an `error.code: [ERROR_CODE]`
```

### From FS Validation Rules

**FS Pattern:**
```
"The system shall [require/ensure/validate] [constraint]"
```

**Derived Tests:**
- Positive: Valid input meeting constraint
- Negative: Invalid input violating constraint
- Edge: Boundary values of constraint

### From FS Authorization Rules

**FS Pattern:**
```
"The system shall allow [actor] to [action]"
"The system shall prevent [actor] from [action]"
```

**Derived Tests:**
- Security test for each allowed/denied actor combination

---

## Checklist for Test Case Generation

For each SRS requirement, ensure:

- [ ] At least one positive test (P-001)
- [ ] Negative test for missing required fields (N-001)
- [ ] Negative test for data store failure (N-00X)
- [ ] Negative test for not found (if applicable)
- [ ] Negative test for immutable field modification (if applicable)
- [ ] Negative test for dependency conflicts (if applicable)
- [ ] Security test for out-of-scope access (if scoped)
- [ ] Edge cases for field boundaries (if constraints exist)