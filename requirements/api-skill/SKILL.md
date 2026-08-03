---
name: api-skill
description: RESTful API design conventions for back-end systems.
disable-model-invocation: true
---

# API Design

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

| Topic | Document | Description |
|-------|----------|-------------|
| HTTP Methods & Patterns | [rest-conventions.md](docs/rest-conventions.md) | HTTP methods, resource patterns, field naming, headers |
| Naming Guidelines | [naming-guidelines.md](docs/naming-guidelines.md) | Avoid abbreviations, flat nouns, no module roots |
| Path Structure | [path-structure.md](docs/path-structure.md) | Feature separation, config vs runtime APIs |
| Error Handling | [error-handling.md](docs/error-handling.md) | Error response format, common codes |
| Pagination & Filtering | [pagination-filtering.md](docs/pagination-filtering.md) | Pagination, filtering, sorting patterns |
| Batch Operations | [bulk-operations.md](docs/bulk-operations.md) | Sync batch (207 Multi-Status), async batch (202 Accepted with job tracking) |
| Versioning | [versioning.md](docs/versioning.md) | Path versioning, deprecation guidelines |
| Payload Structure | [payload-structure.md](docs/payload-structure.md) | Nested vs flat structures, domain boundaries, extensibility |
