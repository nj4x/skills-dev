# Batch Operations

This document defines patterns for designing batch API endpoints that process multiple items in a single request. Two distinct patterns are provided: **Synchronous Batch** for immediate per-item results, and **Asynchronous Batch** for background job processing.

---

## Endpoint Design

Always use a **dedicated batch endpoint** separate from single-item endpoints:

```
POST /resources           # Single item creation
POST /resources/batch     # Batch creation (sync or async)
```

**Benefits:**
- Clear separation of single vs batch operations
- Different validation, rate limits, and timeouts per endpoint
- Easier to document and version independently
- No ambiguity in request/response contract

**Naming Convention:**

| Operation | Method | Path |
|-----------|--------|------|
| Batch Create | POST | `/resources/batch` |
| Batch Update | PATCH | `/resources/batch` |
| Batch Delete | POST | `/resources/batch-delete` |

Use `POST` (not `DELETE`) for batch delete because the request requires a body with the list of IDs.

---

## Choosing Sync vs Async

| Criteria | Synchronous Batch | Asynchronous Batch |
|----------|-------------------|--------------------|
| **Item count** | Small to medium (typically ≤ 100) | Large (100+, up to configurable max) |
| **Processing time** | Completes within HTTP timeout (~30s) | Exceeds HTTP timeout |
| **Result delivery** | Immediate per-item results in response | Results via status endpoint or external system |
| **Use case** | Interactive operations needing instant feedback | Background jobs, import operations, bulk provisioning |
| **Business requirement** | Caller needs to act on each result immediately | Caller can poll or be notified later |

**Decision rule**: If the operation is always long-running regardless of item count, or if the business requirement mandates background processing, use the **Asynchronous** pattern. Otherwise, default to **Synchronous**.

---

## Synchronous Batch Pattern

For batch operations that complete within a single HTTP request/response cycle.

### Request Format

Batch request items use the **same schema** as single-item requests:

```json
{
  "items": [
    { "name": "Item 1", "type": "A" },
    { "name": "Item 2", "type": "B" },
    { "name": "Item 3", "type": "A" }
  ]
}
```

**Schema Consistency Rule:**
- ✅ Each item in `items` array uses the same schema as single-item POST
- ❌ Do not create a separate "batch schema" with different field names

### Response Format

Use **207 Multi-Status** to report per-item results:

```json
{
  "results": [
    { "index": 0, "status": 201, "data": { "id": "123", "name": "Item 1" } },
    { "index": 1, "status": 400, "error": { "code": "INVALID_FIELD", "message": "Invalid type" } },
    { "index": 2, "status": 201, "data": { "id": "125", "name": "Item 3" } }
  ],
  "summary": {
    "total": 3,
    "succeeded": 2,
    "failed": 1
  }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `results` | array | Per-item results in request order |
| `results[].index` | integer | Position in the request array (0-indexed) |
| `results[].status` | integer | HTTP status code for this item |
| `results[].data` | object | Created/updated resource (on success) |
| `results[].error` | object | Error object (on failure) |
| `summary.total` | integer | Total items in request |
| `summary.succeeded` | integer | Count of successful operations |
| `summary.failed` | integer | Count of failed operations |

### Performance Limits

| Constraint | Recommended Value | Notes |
|------------|-------------------|-------|
| Max items per request | 100–1000 | Configurable per endpoint |
| Timeout threshold | ~30 seconds | Must complete within HTTP timeout |

### Validation

Validate item count before processing. Return 400 immediately if limit exceeded:

```json
{
  "error": {
    "code": "TOO_MANY_ITEMS",
    "message": "Batch request exceeds maximum of 100 items"
  }
}
```

---

## Asynchronous Batch Pattern

For operations that require background processing — either because of large item counts, extended per-item processing time, or explicit business requirements for async behavior.

### Endpoint Design

The batch submission and status tracking share the same base path:

```
POST   /resources/batch             # Submit batch job
GET    /resources/batch/{batchId}   # Get batch job status/results
```

This keeps the batch API self-contained under the resource it operates on, without requiring a separate generic `/jobs` endpoint.

### Submit Request

```
POST /resources/batch
```

```json
{
  "items": [
    { "name": "Item 1", "type": "A" },
    { "name": "Item 2", "type": "B" }
  ]
}
```

**Schema Consistency Rule** applies the same as synchronous — each item uses the single-item schema.

### Submit Response (202 Accepted)

```json
{
  "batchId": "uuid",
  "status": "ACCEPTED",
  "statusUrl": "/resources/batch/{batchId}",
  "submittedAt": "2025-02-10T10:00:00Z",
  "summary": {
    "total": 2
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `batchId` | string (UUID) | Unique identifier for the batch job |
| `status` | string | Initial status: `ACCEPTED` |
| `statusUrl` | string | URL to poll for batch status |
| `submittedAt` | datetime | When the batch was submitted |
| `summary.total` | integer | Total items submitted |

### Status Endpoint

```
GET /resources/batch/{batchId}
```

### Status Response — In Progress

```json
{
  "batchId": "uuid",
  "status": "PROCESSING",
  "progress": {
    "processed": 250,
    "total": 500
  }
}
```

### Status Response — Completed

```json
{
  "batchId": "uuid",
  "status": "COMPLETED",
  "completedAt": "2025-02-10T12:00:00Z",
  "summary": {
    "total": 500,
    "succeeded": 495,
    "failed": 5
  },
  "resultsUrl": "/resources/batch/{batchId}/results"
}
```

### Batch Status Values

| Status | Description |
|--------|-------------|
| `ACCEPTED` | Batch accepted, queued for processing |
| `PROCESSING` | Batch in progress |
| `COMPLETED` | Batch finished (check summary for success/failure counts) |
| `FAILED` | Batch failed entirely (system error) |

### Performance Limits

| Constraint | Recommended Value | Notes |
|------------|-------------------|-------|
| Max items per request | 1000–10000 | Higher than sync since processing is background |
| Status polling interval | 2–10 seconds | Recommended client-side polling frequency |

### Nested Resource Paths

When the batch operates on a sub-resource, nest the `/batch` path under the parent:

```
POST   /groups/{id}/members/batch              # Submit batch add members
GET    /groups/{id}/members/batch/{batchId}     # Get batch status
```

---

## Batch Delete Pattern

**Avoid** using DELETE for batch operations — use POST with an action indicator:

```
POST /resources/batch-delete
```

```json
{
  "ids": ["id1", "id2", "id3"]
}
```

**Response (Synchronous — 207 Multi-Status):**

```json
{
  "results": [
    { "index": 0, "status": 204, "id": "id1" },
    { "index": 1, "status": 404, "id": "id2", "error": { "code": "NOT_FOUND" } },
    { "index": 2, "status": 204, "id": "id3" }
  ],
  "summary": {
    "total": 3,
    "succeeded": 2,
    "failed": 1
  }
}
```

For large-scale deletes, the asynchronous pattern can be applied with `POST /resources/batch-delete` returning 202 Accepted and status tracked at `GET /resources/batch-delete/{batchId}`.

---

## Summary

| Aspect | Synchronous Batch | Asynchronous Batch |
|--------|-------------------|--------------------|
| **Endpoint** | `POST /resources/batch` | `POST /resources/batch` |
| **Status tracking** | N/A (inline response) | `GET /resources/batch/{batchId}` |
| **Response code** | 207 Multi-Status | 202 Accepted |
| **Result delivery** | Per-item results in response body | Via status endpoint or external system |
| **Schema** | Same as single item | Same as single item |
| **Max items** | 100–1000 (within HTTP timeout) | 1000–10000 (background processing) |
| **Use when** | Immediate feedback needed, small batches | Large batches, long-running operations |
| **HTTP verb** | POST (create/delete), PATCH (update) | POST (create/delete), PATCH (update) |