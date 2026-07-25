# API Definition Document Structure

This document defines the standard structure for detailed API Definition documents that accompany SRS documents. While the SRS contains a summary API Reference, this companion document provides full specifications.

## Document Template

```markdown
# [Domain Name] | API Definition

## Document Information

| Field | Value |
|-------|-------|
| **Document ID** | [DOMAIN]-API-Definition-[VERSION] |
| **Category** | API Definition |
| **Version** | [Major.Minor] |
| **Status** | [Draft/Review/Final] |
| **Created** | [Date] |
| **Related SRS** | [SRS Document ID] |
| **Base URL** | [Base URL for the API] |

---

## API Overview

### API Categories

| Category | Base Path | Description |
|----------|-----------|-------------|
| Internal | /internal/ | Service-to-service APIs within the platform |
| Administrative | /v2/ | Client-facing APIs |

### Authentication

[Description of authentication mechanism, e.g., access tokens, API keys]

### Common Headers

| Header | Required | Description |
|--------|----------|-------------|
| Authorization | Yes | Bearer token for authentication |
| Content-Type | Yes | application/json |

---

## Internal APIs

### [[DOMAIN]-API-001] [Operation Name]

**Endpoint**: `[HTTP Method] /internal/[resource-path]`

**Since**: Version [X.Y]

> **⚠️ "Since" Version Rule**: Use the version from the **Document ID** (e.g., `2.0` from `GRP-API-Definition-2.0`), NOT the frequently-updated `Version` field in the Document Information table (e.g., `2.29`). The Document ID version represents the feature release version in which this API was introduced.

**Description**: [Detailed description of what this API does]

#### Request

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| [paramName] | [type] | Yes/No | [description] |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| [paramName] | [type] | Yes/No | [default] | [description] |

**Request Headers:**

| Header | Required | Description |
|--------|----------|-------------|
| [headerName] | Yes/No | [description] |

**Request Body:**

```json
{
  "[fieldName]": "[type] - [description]",
  "[fieldName]": "[type] - [description]"
}
```

**Request Body Schema:**

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| [fieldName] | [type] | Yes/No | [constraints] | [description] |

#### Response

**Success Response (2XX):**

| Status Code | Condition |
|-------------|-----------|
| [200/201/204] | [When this status is returned] |

**Response Body:**

```json
{
  "[fieldName]": "[type]",
  "[fieldName]": "[type]"
}
```

**Response Body Schema:**

| Field | Type | Description |
|-------|------|-------------|
| [fieldName] | [type] | [description] |

**Error Responses:**

| Status Code | Error Code | Condition |
|-------------|------------|-----------|
| 400 | [ERROR_CODE] | [When this error occurs] |
| 403 | [ERROR_CODE] | [When this error occurs] |
| 404 | [ERROR_CODE] | [When this error occurs] |
| 409 | [ERROR_CODE] | [When this error occurs] |
| 500 | [ERROR_CODE] | [When this error occurs] |

#### Example

**Request:**

```http
[HTTP Method] /internal/[path]
Content-Type: application/json
Authorization: Bearer <token>

{
  "[fieldName]": "[exampleValue]"
}
```

**Response (Success):**

```http
HTTP/1.1 [StatusCode] [StatusText]
Content-Type: application/json

{
  "[fieldName]": "[exampleValue]"
}
```

**Response (Error):**

```http
HTTP/1.1 [ErrorStatusCode] [ErrorStatusText]
Content-Type: application/json

{
  "error": {
    "code": "[ERROR_CODE]",
    "message": "[Error message]"
  }
}
```

#### Related Requirements

| SRS Requirement | Description |
|-----------------|-------------|
| [SRS-X.0.0] | [Brief requirement description] |

---

## Administrative APIs

### [[DOMAIN]-API-101] [Operation Name]

[Same structure as Internal APIs above]

---

## Common Data Types

### [TypeName]

[Description of the data type]

```json
{
  "[field1]": "[type]",
  "[field2]": "[type]"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| [field1] | [type] | Yes/No | [description] |
| [field2] | [type] | Yes/No | [description] |

---

## API Design Conventions

> **Note**: For API design conventions (error handling, pagination, filtering, sorting, versioning), refer to **api-skill**.

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| [X.Y] | [Date] | [Author] | [Change description] |
```

---

## API Documentation Guidelines

### Naming Conventions

1. **API IDs**: Use domain-prefixed sequential numbering per category
   - Format: `[DOMAIN]-API-[NUMBER]`
   - Internal APIs: [DOMAIN]-API-001, [DOMAIN]-API-002, ... (001-099)
   - Administrative APIs: [DOMAIN]-API-101, [DOMAIN]-API-102, ... (101-199)
   - Me APIs: [DOMAIN]-API-201, [DOMAIN]-API-202, ... (201-299)
   - Examples: `GRP-API-001`, `GRP-API-101`, `ROLE-API-001`

2. **Path Names**: Use kebab-case for multi-word paths
   - ✅ `/system-roles`, `/user-groups`
   - ❌ `/systemRoles`, `/user_groups`

3. **Field Names**: Use camelCase for JSON fields
   - ✅ `roleName`, `createdAt`
   - ❌ `role_name`, `RoleName`

### Required Elements

Every API definition MUST include:

- [ ] Unique API ID
- [ ] HTTP method and endpoint path
- [ ] Version introduced (Since)
- [ ] Full request specification (parameters, body, headers)
- [ ] Full response specification (success and error)
- [ ] At least one request/response example
- [ ] Related SRS requirements

### Best Practices

1. **Be Explicit**: Document all possible responses, including edge cases
2. **Provide Examples**: Include realistic examples for requests and responses
3. **Document Constraints**: Clearly state field constraints (min/max length, allowed values)
4. **Link to Requirements**: Always reference the source SRS requirements
5. **Keep Updated**: Update API documentation when implementation changes

---

## Relationship to SRS

| SRS Section | API Definition Section |
|-------------|------------------------|
| API Reference (summary) | Full API specifications |
| Entity Reference | Common Data Types |
| Error Code Reference | Error Response Format |
| Test Cases | Used for API examples |

The API Definition document expands on the summary API Reference in the SRS, providing implementation-level detail needed by developers.