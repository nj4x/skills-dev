---
name: api-skill
description: Documents RESTful API design best practices for back-end systems. Use this skill when designing new APIs, reviewing existing APIs, or ensuring consistency across API endpoints. Provides guidance on naming conventions, error handling, pagination, versioning, and bulk operations. Keywords - REST, API design, HTTP methods, error handling, pagination, bulk API, API conventions.
---

# API Design Skill

This skill documents RESTful API design best practices agreed for use in our systems. It provides:
- HTTP method semantics and usage patterns
- Naming conventions for paths and fields
- Error handling standards
- Pagination and filtering patterns
- Batch operation guidelines (sync and async patterns)
- Versioning and deprecation strategies

---

## When to Use This Skill

Use this skill when:
- Designing new API endpoints
- Reviewing existing API designs for consistency
- Implementing error handling patterns
- Adding pagination, filtering, or sorting to endpoints
- Designing batch operation endpoints
- Planning API versioning or deprecation

---

## Quick Reference

### HTTP Methods

| Method | Purpose | Success Code |
|--------|---------|--------------|
| GET | Retrieve resource(s) | 200 |
| POST | Create new resource | 201 |
| PATCH | Partial update | 200 |
| PUT | Full replacement/upsert | 200/201 |
| DELETE | Remove resource | 204 |

### Naming Conventions

| Element | Format | Examples |
|---------|--------|----------|
| URL paths | kebab-case | `/system-roles`, `/user-groups` |
| JSON fields | camelCase | `roleName`, `createdAt` |
| Resource names | Flat nouns | `/federated-auth-configurations` |

### Key Status Codes

| Status | When to Use |
|--------|-------------|
| 200 | Successful GET, PATCH, PUT |
| 201 | Successful POST (created) |
| 207 | Synchronous batch with mixed results |
| 202 | Asynchronous batch accepted |
| 400 | Validation errors |
| 404 | Resource not found |
| 409 | State conflict |

---

## Reference Documentation

For detailed guidelines, see the following documents:

| Topic | Document | Description |
|-------|----------|-------------|
| HTTP Methods & Patterns | [rest-conventions.md](<skill dir>/docs/rest-conventions.md) | HTTP methods, resource patterns, field naming, headers |
| Naming Guidelines | [naming-guidelines.md](<skill dir>/docs/naming-guidelines.md) | Avoid abbreviations, flat nouns, no module roots |
| Path Structure | [path-structure.md](<skill dir>/docs/path-structure.md) | Feature separation, config vs runtime APIs |
| Error Handling | [error-handling.md](<skill dir>/docs/error-handling.md) | Error response format, common codes |
| Pagination & Filtering | [pagination-filtering.md](<skill dir>/docs/pagination-filtering.md) | Pagination, filtering, sorting patterns |
| Batch Operations | [bulk-operations.md](<skill dir>/docs/bulk-operations.md) | Sync batch (207 Multi-Status), async batch (202 Accepted with job tracking) |
| Versioning | [versioning.md](<skill dir>/docs/versioning.md) | Path versioning, deprecation guidelines |
| Payload Structure | [payload-structure.md](<skill dir>/docs/payload-structure.md) | Nested vs flat structures, domain boundaries, extensibility |
