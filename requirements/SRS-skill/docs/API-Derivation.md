# API Derivation Guide

This document provides rules and patterns for deriving API specifications from Feature Set (FS) requirements when creating SRS documents.

## API Derivation Overview

API derivation transforms high-level FS requirements into concrete REST API specifications including:
- HTTP methods and endpoints
- Request/response formats
- Status codes and error handling
- Query parameters and filters

---

## CRUD to REST Mapping

### Standard Mappings

| CRUD Operation | HTTP Method | Path Pattern | Success Status |
|----------------|-------------|--------------|----------------|
| Create | POST | `/[resources]` | 201 Created |
| Read (single) | GET | `/[resources]/{id}` | 200 OK |
| Read (list) | GET | `/[resources]` | 200 OK |
| Update (partial) | PATCH | `/[resources]/{id}` | 200 OK |
| Update (full) | PUT | `/[resources]/{id}` | 200 OK |
| Delete | DELETE | `/[resources]/{id}` | 204 No Content |

### Resource Naming

1. **Use plural nouns** for collections
   - ✅ `/roles`, `/groups`, `/users`
   - ❌ `/role`, `/group`, `/user`

2. **Use kebab-case** for multi-word resources
   - ✅ `/system-roles`, `/custom-roles`
   - ❌ `/systemRoles`, `/system_roles`

3. **Use lowercase** for all paths
   - ✅ `/api/v2/roles`
   - ❌ `/api/V2/Roles`

---

## API Classification

### Internal APIs

For system-to-system communication within the SAB platform:

| Prefix | Access | Use Case |
|--------|--------|----------|
| `/internal/` | Service-to-service only | System role management, internal operations |

**Characteristics:**
- **Created strictly on a per-need-basis** by other systems within the SAB platform
- Not exposed to external clients
- Higher trust level
- May skip certain validations
- Often used by admin tools

> **Important**: Internal APIs should only be created when there is a concrete need from another SAB platform system. Do not speculatively design internal APIs—derive them from explicit integration requirements.

**Example:**
```
POST /internal/system-roles
GET /internal/system-roles/{roleId}
PATCH /internal/system-roles/{roleId}
DELETE /internal/system-roles/{roleId}
```

### Administrative APIs

For client-facing operations:

| Prefix | Access | Use Case |
|--------|--------|----------|
| `/v2/` | Client applications | Custom role management, user operations |
| `/v3/` | New version | Breaking changes, new features |

**Characteristics:**
- Exposed to external clients
- Requires authentication
- Full authorization checks
- Rate limiting applied

**Example:**
```
POST /v2/custom-roles
GET /v2custom-roles/{roleId}
PATCH /v2/custom-roles/{roleId}
DELETE /v2/custom-roles/{roleId}
```

---

## Deriving Endpoints from FS Requirements

### Pattern 1: Create Operations

**FS Pattern:**
```
"The system shall create [entity] with [attributes]"
"The system shall provide functionality to create [entity]"
```

**Derived API:**
```markdown
**Endpoint**: POST /[prefix]/[resources]

**Request Body**:
{
  "[attribute1]": "[type]",
  "[attribute2]": "[type]"
}

**Response** (201 Created):
{
  "[entityId]": "[generated-id]",
  "[attribute1]": "[value]",
  "version": 1
}
```

**Example:**
```
FS: "The system shall take RoleName, RoleDescription(optional), PrivilegeList as inputs"
FS: "The system shall create a new system role and return the RoleId, and Version:1"

POST /internal/system-roles
Request:
{
  "roleName": "Admin",
  "roleDescription": "Administrator role",
  "privilegeList": ["priv1", "priv2"]
}

Response (201):
{
  "roleId": "uuid-here",
  "roleName": "Admin",
  "roleDescription": "Administrator role",
  "privilegeList": ["priv1", "priv2"],
  "isSystemRole": true,
  "version": 1
}
```

### Pattern 2: Read Operations (Single)

**FS Pattern:**
```
"The system shall return [attributes] for [entity]"
"The system shall provide functionality to view [entity] details"
```

**Derived API:**
```markdown
**Endpoint**: GET /[prefix]/[resources]/{id}

**Path Parameters**:
- `id`: [Entity] identifier

**Response** (200 OK):
{
  "[entityId]": "[value]",
  "[attribute1]": "[value]",
  "[attribute2]": "[value]"
}
```

### Pattern 3: Read Operations (List)

**FS Pattern:**
```
"The system shall list all [entities]"
"The system shall allow searching by [field]"
"The system shall allow filtering by [criteria]"
"The system shall allow sorting by [field]"
```

**Derived API:**
```markdown
**Endpoint**: GET /[prefix]/[resources]

**Query Parameters**:
- `search`: Search term (pattern matching)
- `filter[field]`: Filter by specific field
- `sortBy`: Sort field name
- `sortOrder`: asc | desc (default: asc)
- `page`: Page number (default: 1)
- `pageSize`: Items per page (default: 20, max: 100)

**Response** (200 OK):
{
  "items": [...],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 100,
    "totalPages": 5
  }
}
```

### Pattern 4: Update Operations

**FS Pattern:**
```
"The system shall provide functionality to update [attributes]"
"The system shall not allow change to [attribute]"
```

**Derived API:**
```markdown
**Endpoint**: PATCH /[prefix]/[resources]/{id}

**Path Parameters**:
- `id`: [Entity] identifier

**Request Body** (partial update):
{
  "[mutableAttribute1]": "[new-value]",
  "[mutableAttribute2]": "[new-value]"
}

**Response** (200 OK):
{
  "[entityId]": "[value]",
  "[attribute1]": "[updated-value]",
  "version": [incremented]
}
```

### Pattern 5: Delete Operations

**FS Pattern:**
```
"The system shall delete [entity]"
"The system shall take confirmation before deletion"
"The system shall check if [entity] has [dependencies]"
```

**Derived API:**
```markdown
**Endpoint**: DELETE /[prefix]/[resources]/{id}

**Path Parameters**:
- `id`: [Entity] identifier

**Query Parameters**:
- `confirm`: Boolean (required if confirmation needed)

**Response** (204 No Content): Empty body
```

---

## Query Parameter Patterns

### Search

```
GET /resources?search={term}
```

**FS Source:**
```
"The system shall allow searching by RoleName pattern matching and RoleId exact matching"
```

### Filtering

```
GET /resources?filter[field]=value
GET /resources?privilege=priv1  (shorthand for expensive filters)
```

**FS Source:**
```
"The system shall allow filtering the list by a particular Privilege"
```

### Sorting

```
GET /resources?sortBy=fieldName&sortOrder=asc
```

**FS Source:**
```
"The system shall allow sorting the list by RoleName (lexicographically)"
```

### Pagination

```
GET /resources?page=1&pageSize=20
```

Default behavior for list operations.

---

## Status Codes

### Success Codes

| Code | Meaning | Use Case |
|------|---------|----------|
| 200 OK | Request succeeded | GET, PATCH, PUT |
| 201 Created | Resource created | POST |
| 204 No Content | Success, no body | DELETE |

### Client Error Codes

| Code | Meaning | Error Code Pattern |
|------|---------|-------------------|
| 400 Bad Request | Invalid input | `BAD_REQUEST`, `INVALID_FIELD` |
| 401 Unauthorized | Not authenticated | `UNAUTHORIZED` |
| 403 Forbidden | No permission | `FORBIDDEN`, `OUT_OF_SCOPE` |
| 404 Not Found | Resource missing | `NOT_FOUND`, `RESOURCE_NOT_FOUND` |
| 409 Conflict | State conflict | `CONFLICT`, `HAS_DEPENDENCIES` |

### Server Error Codes

| Code | Meaning | Error Code Pattern |
|------|---------|-------------------|
| 500 Internal Server Error | System failure | `INTERNAL_SERVER_ERROR` |
| 503 Service Unavailable | Temporary unavailable | `SERVICE_UNAVAILABLE` |

---

## Error Response Format

Standard error response structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": [
      {
        "field": "fieldName",
        "message": "Field-specific error"
      }
    ]
  }
}
```

### Common Error Codes

| Error Code | HTTP Status | Trigger |
|------------|-------------|---------|
| `BAD_REQUEST` | 400 | Missing required fields |
| `INVALID_SORT_FIELD` | 400 | Invalid sort parameter |
| `INVALID_FILTER` | 400 | Invalid filter parameter |
| `CONFIRMATION_REQUIRED` | 400 | Delete without confirmation |
| `IDENTIFIER_IMMUTABLE` | 400 | Attempt to change ID |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `OUT_OF_SCOPE` | 403 | Outside organization scope |
| `NOT_ACCESSIBLE` | 403 | Resource not visible to user |
| `NOT_FOUND` | 404 | Resource does not exist |
| `HAS_ACTIVE_ASSIGNMENTS` | 409 | Cannot delete assigned resource |
| `INTERNAL_SERVER_ERROR` | 500 | Internal server error |

---

## API Documentation Format

### Endpoint Specification Template

```markdown
### [Operation Name]

**Method**: [HTTP Method]
**Path**: [Endpoint path]
**Access**: Internal | Administrative
**Since**: Version X.Y (use the version from the **Document ID**, e.g., `2.0` from `GRP-SRS-2.0`, not the frequently-updated Document Information Version)

#### Request

**Path Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| [param] | [type] | Yes/No | [description] |

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| [param] | [type] | Yes/No | [default] | [description] |

**Request Body:**
```json
{
  "[field]": "[type] - [description]"
}
```

#### Response

**Success Response** ([Status Code]):
```json
{
  "[field]": "[type]"
}
```

**Error Responses:**
| Status | Error Code | Condition |
|--------|------------|-----------|
| 400 | BAD_REQUEST | [When triggered] |
| 404 | NOT_FOUND | [When triggered] |
```

---

## Special API Patterns

### Confirmation-Required Deletions

For operations requiring explicit confirmation:

```
DELETE /resources/{id}?confirm=true
```

Without `confirm=true`:
```json
{
  "error": {
    "code": "CONFIRMATION_REQUIRED",
    "message": "Deletion requires explicit confirmation"
  }
}
```

### Scope-Limited Operations

For operations scoped to organization:

```
GET /v2/custom-roles
```

Implicit scope from authentication context (access token contains organizationId).

### Bulk Operations

For operations on multiple resources:

```
POST /resources/bulk-delete
{
  "ids": ["id1", "id2", "id3"],
  "confirm": true
}
```

---

## Authorization Derivation

### From FS Permission Matrices

**FS Source:**
```
| Privilege | Super Admin | Group Admin | Owner | Manager | Member |
|-----------|-------------|-------------|-------|---------|--------|
| Create    | ✓           | ✓*          | ✗     | ✗       | ✗      |
```

**Derived Authorization:**
```
POST /resources
- Requires: Super Admin OR Group Admin (with permission)
- Deny: Owner, Manager, Member
```

### Actor-Based Access

**FS Source:**
```
"Actor: SAB Role Management Owner (CRUD); SAB Client Organizations (R)"
```

**Derived Access Control:**
```
/internal/system-roles:
  - POST, PATCH, DELETE: SAB Role Management Owner only
  - GET: SAB Role Management Owner OR SAB Client Organizations
```

---

## Extraction Checklist

When deriving APIs from FS requirements:

- [ ] What CRUD operations are defined?
- [ ] What entities are being operated on?
- [ ] Is this internal or administrative facing?
- [ ] What input attributes are required/optional?
- [ ] What output attributes should be returned?
- [ ] What search/filter/sort capabilities are needed?
- [ ] What confirmation requirements exist?
- [ ] What authorization rules apply?
- [ ] What error conditions are possible?
- [ ] What dependencies might prevent operations?