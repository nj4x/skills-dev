# REST Conventions

This document defines RESTful API conventions for HTTP methods, resource patterns, and field naming.

---

## HTTP Methods

| Method | Purpose | Idempotent | Request Body | Success Code |
|--------|---------|------------|--------------|--------------|
| GET | Retrieve resource(s) | Yes | No | 200 |
| POST | Create new resource | No | Yes | 201 |
| PATCH | Partial update | No | Yes | 200 |
| PUT | Full replacement/upsert | Yes | Yes | 200/201 |
| DELETE | Remove resource | Yes | No | 204 |

### Usage Guidelines

- **GET**: Use for all read operations. Never modify state.
- **POST**: Use for creation. Return the created resource with its ID.
- **PATCH**: Preferred for updates. Only send fields being changed.
- **PUT**: Use only for full replacement or upsert operations.
- **DELETE**: Use for removal. Consider requiring confirmation for destructive operations.

---

## Resource Path Patterns

### Standard CRUD Operations

```
GET    /[resources]              # List resources
POST   /[resources]              # Create resource
GET    /[resources]/{id}         # Get single resource
PATCH  /[resources]/{id}         # Update resource
DELETE /[resources]/{id}         # Delete resource
```

### Nested Resources

Use nested paths when resources have a clear parent-child relationship:

```
GET    /organizations/{orgId}/members          # List members in org
POST   /organizations/{orgId}/members          # Add member to org
DELETE /organizations/{orgId}/members/{userId} # Remove member
```

### Query Parameters Over Dedicated Endpoints

**Prefer adding query parameters to existing list endpoints** over creating standalone lookup/filter endpoints. This reduces API surface area and keeps filtering consistent.

**❌ Avoid** creating a dedicated endpoint for a specific filter:
```
GET /groups-by-role?roleId={roleId}    # Dedicated endpoint for one filter
GET /users-by-department?deptId={id}   # Another single-purpose endpoint
```

**✅ Prefer** adding the filter as a query parameter on the existing list endpoint:
```
GET /groups?adminRoleId={roleId}       # Filter on existing list endpoint
GET /users?departmentId={id}           # Filter on existing list endpoint
```

**When this applies:**
- The filter returns the same resource type as the list endpoint
- The filter can be combined with other existing filters (pagination, sorting, search)
- The result shape is the same or a subset of the standard list response

**When a dedicated endpoint is justified:**
- The result shape is fundamentally different from the list response
- The operation has different authentication/authorization requirements
- Performance requirements necessitate a separate optimized path

---

## Field Naming

Use **camelCase** for JSON field names:
- ✅ `roleName`, `createdAt`, `isActive`, `pageSize`
- ❌ `role_name`, `RoleName`, `ROLE_NAME`

## Payload Structure

For resources with metadata or complex domain models, use nested structures to separate control flags from business data. See [payload-structure.md](<skill dir>/docs/payload-structure.md) for detailed guidelines on when to use nested vs flat payload structures.

**Example - Preferred structure with clear domain boundary:**
```json
{
  "inherited": false,
  "policies": {
    "mfaRequired": true,
    "password": "VERY_STRONG"
  }
}
```

---

## Common Headers

| Header | Required | Description |
|--------|----------|-------------|
| Content-Type | Yes | `application/json` |
| Authorization | Yes | Bearer token or API key |

### API Gateway-Injected Headers

For all **external APIs** (paths under `/v2/`), the API Gateway (ApiGW) extracts claims from the caller's access token and injects the following headers into the upstream request. These headers are **not sent by API clients** — they are added by the gateway and are available to all back-end services.

| Header | Source | Description |
|--------|--------|-------------|
| `sa-authorized-org-id` | Access token | The organization ID of the API caller. Use as the organization context for the request (e.g., scoping data, authorization checks). |
| `sa-authorized-user-id` | Access token | The user ID of the API caller. Use as the acting user identity (e.g., `createdBy`, `updatedBy` audit fields). |

**Usage notes:**
- These headers replace the need for `organizationId` or `userId` in request bodies on external APIs — the caller's identity is established by the gateway from the access token.
- Internal APIs (`/internal/`) do NOT receive these headers; they must pass context explicitly in request bodies or their own headers.
- Back-end services should treat these headers as trusted (the gateway validates the access token before injecting them).

### Response Headers for Rate Limiting

| Header | Description |
|--------|-------------|
| X-RateLimit-Limit | Max requests per window |
| X-RateLimit-Remaining | Remaining requests |
| X-RateLimit-Reset | Unix timestamp when window resets |