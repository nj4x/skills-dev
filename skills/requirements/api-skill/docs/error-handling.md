# Error Handling

This document defines the standard error response format and common error codes for API responses.

---

## Standard Error Response Format

All error responses follow this structure:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message"
  }
}
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `error.code` | string | Yes | Machine-readable error code |
| `error.message` | string | Yes | Human-readable description |

---

## HTTP Status Code Guidelines

| Status | When to Use |
|--------|-------------|
| 200 OK | Successful GET, PATCH, PUT |
| 201 Created | Successful POST (resource created) |
| 202 Accepted | Async operation accepted for processing |
| 204 No Content | Successful DELETE |
| 207 Multi-Status | Bulk operation with mixed results |
| 400 Bad Request | Validation errors, malformed request |
| 401 Unauthorized | Missing or invalid authentication |
| 403 Forbidden | Valid auth but insufficient permissions |
| 404 Not Found | Resource does not exist |
| 409 Conflict | State conflict (duplicate, dependencies) |
| 500 Internal Server Error | Unexpected server-side errors |

---

## Common Error Codes

### Client Errors (4xx)

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| BAD_REQUEST | 400 | Request validation failed |
| INVALID_FIELD | 400 | Invalid field value |
| MISSING_REQUIRED_FIELD | 400 | Required field not provided |
| CONFIRMATION_REQUIRED | 400 | Destructive operation requires confirmation |
| UNAUTHORIZED | 401 | Authentication failed or missing |
| FORBIDDEN | 403 | Insufficient permissions |
| OUT_OF_SCOPE | 403 | Resource outside user's access scope |
| NOT_FOUND | 404 | Resource does not exist |
| CONFLICT | 409 | Operation conflicts with current state |
| HAS_DEPENDENCIES | 409 | Cannot delete due to active dependencies |

### Server Errors (5xx)

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| INTERNAL_SERVER_ERROR | 500 | Unexpected server error |

---

## Error Response Examples

### Validation Error (400)

```json
{
  "error": {
    "code": "BAD_REQUEST",
    "message": "Request validation failed"
  }
}
```

### Not Found (404)

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Resource not found"
  }
}
```

### Conflict (409)

```json
{
  "error": {
    "code": "HAS_DEPENDENCIES",
    "message": "Cannot delete role with active assignments"
  }
}
```

### Forbidden (403)

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Insufficient permissions to perform this operation"
  }
}