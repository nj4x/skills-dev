# Pagination & Filtering

This document defines standard patterns for pagination, filtering, and sorting in list APIs.

---

## Pagination

### Pagination Strategies

Two pagination strategies are supported. Choose based on UX requirements:

| Strategy | Best For | Client Knows Total? | Supports Jump-to-Page? |
|----------|----------|---------------------|------------------------|
| **Tag-based** (preferred) | Infinite scroll, load-more UX | No | No |
| **Offset-based** | Admin dashboards, page-number navigation | Yes | Yes |

---

### Tag-based Pagination (Preferred)

Use tag-based pagination when the UX uses infinite scroll or "load more" patterns, where the total number of items/pages is not known or needed ahead of time.

#### Request Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `pageSize` | Integer | 20 | 100 | Number of items to return per batch |
| `pageTag` | String | — | — | Opaque token from previous response to fetch the next batch. Omit for the first request. |

#### Response Format

**When more items exist:**

```json
{
  "items": [...],
  "nextPageTag": "eyJsYXN0SWQiOiI1NTBlODQwMC4uLiJ9"
}
```

**Last page (no more items):**

```json
{
  "items": [...]
}
```

#### Response Fields

| Field | Type | Presence | Description |
|-------|------|----------|-------------|
| `items` | Array | Always | The batch of results |
| `nextPageTag` | String | Conditional | Opaque token for retrieving the next batch. **Present only when more items exist.** Absent on the last page. |

#### How It Works

1. Client requests the first page: `GET /resources?pageSize=20`
2. Server returns items and `nextPageTag` (if more exist)
3. Client requests the next page: `GET /resources?pageSize=20&pageTag=<nextPageTag>`
4. Repeat until response has no `nextPageTag` — the client has reached the end

#### Token Design

- The `nextPageTag` value is **opaque to the client** — clients must not parse, construct, or modify it
- The server may encode any state it needs (last-seen ID, offset, sort cursor, filter context, etc.)
- Tokens should be URL-safe (e.g., Base64url-encoded)
- Tokens may be time-limited or single-use at the server's discretion

#### Example

**First request:**

```
GET /v2/groups?pageSize=25
```

**Response:**

```json
{
  "items": [
    { "id": "...", "groupName": "Alpha Team" },
    { "id": "...", "groupName": "Beta Team" }
  ],
  "nextPageTag": "eyJsYXN0SWQiOiI1NTBlODQwMCJ9"
}
```

**Next request:**

```
GET /v2/groups?pageSize=25&pageTag=eyJsYXN0SWQiOiI1NTBlODQwMCJ9
```

**Last page response:**

```json
{
  "items": [
    { "id": "...", "groupName": "Zeta Team" }
  ]
}
```

---

### Offset-based Pagination

Use offset-based pagination only when the UX explicitly requires page-number navigation, total item counts, or jump-to-page functionality.

#### Request Parameters

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | Integer | 1 | — | Page number (1-indexed) |
| `pageSize` | Integer | 20 | 100 | Items per page |

#### Response Format

```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "totalItems": 150,
    "totalPages": 8,
    "hasNextPage": true,
    "hasPreviousPage": false
  }
}
```

#### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `items` | Array | The page of results |
| `pagination.page` | Integer | Current page number |
| `pagination.pageSize` | Integer | Items per page |
| `pagination.totalItems` | Integer | Total count of all items |
| `pagination.totalPages` | Integer | Total number of pages |
| `pagination.hasNextPage` | Boolean | Whether more pages exist after this one |
| `pagination.hasPreviousPage` | Boolean | Whether pages exist before this one |

#### Example Request

```
GET /users?page=2&pageSize=50
```

---

## Filtering

### Bracket Notation

Use bracket notation for filter parameters:

```
GET /resources?filter[status]=active
GET /resources?filter[type]=admin&filter[status]=active
```

### Multiple Values

For filtering by multiple values of the same field, use comma-separated values:

```
GET /resources?filter[status]=active,pending
```

### Nested Fields

For nested object fields, use dot notation inside brackets:

```
GET /resources?filter[owner.id]=123
```

### Filter Operators (Optional)

If your API supports operators beyond equality:

```
GET /resources?filter[createdAt][gte]=2025-01-01
GET /resources?filter[price][lt]=100
```

| Operator | Meaning |
|----------|---------|
| (none) | Equals |
| `gte` | Greater than or equal |
| `gt` | Greater than |
| `lte` | Less than or equal |
| `lt` | Less than |
| `ne` | Not equal |

---

## Sorting

### Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sortBy` | String | — | Field name to sort by |
| `sortOrder` | String | `asc` | Sort direction: `asc` or `desc` |

### Example

```
GET /resources?sortBy=createdAt&sortOrder=desc
GET /users?sortBy=name&sortOrder=asc
```

### Multiple Sort Fields

For APIs that support multiple sort criteria:

```
GET /resources?sort=createdAt:desc,name:asc
```

---

## Combined Examples

### Tag-based with filtering and sorting

```
GET /v2/groups?pageSize=25&filter[status]=active&sortBy=createdAt&sortOrder=desc
```

Next page:

```
GET /v2/groups?pageSize=25&pageTag=eyJsYXN0...&filter[status]=active&sortBy=createdAt&sortOrder=desc
```

### Offset-based with filtering and sorting

```
GET /users?page=1&pageSize=25&filter[status]=active&filter[role]=admin&sortBy=createdAt&sortOrder=desc