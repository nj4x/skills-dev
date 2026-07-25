# Payload Structure Design

This document defines guidelines for designing API request/response payload structures, including when to use nested objects versus flat structures.

---

## When to Use Nested Payload Structures

Nested payload structures provide clear separation between metadata and domain data, offering several key advantages:

### 1. Clear Resource Boundary

**Separate control flags from domain fields:**
- Metadata properties (like `inherited`, `dryRun`, `etag`) describe how the request should be processed
- Domain objects (like `policies`, `settings`, `config`) contain the actual business data

```json
// ✅ Preferred - Clear separation
{
  "inherited": false,
  "policies": {
    "mfaRequired": true,
    "password": "VERY_STRONG"
  }
}

// ❌ Flat structure - Mixed concerns
{
  "inherited": false,
  "mfaRequired": true,
  "password": "VERY_STRONG"
}
```

### 2. Safer Partial Updates

Nested structures make PATCH/merge operations cleaner and less error-prone:

```json
// PATCH request - only policies object is updated
{
  "policies": {
    "mfaRequired": false
  }
}
```

Future fields can be added without conflicting with top-level request options.

### 3. Forward Compatibility

Top-level fields can hold request controls while domain models evolve independently:

```json
// Future extension possibilities
{
  "inherited": false,
  "dryRun": true,
  "etag": "abc123",
  "actor": "user123",
  "reason": "Compliance update",
  "policies": {
    "mfaRequired": true,
    "password": "VERY_STRONG"
  }
}
```

### 4. Consistency with Other APIs

Many APIs use wrapper objects for mutable business fields:
- AWS APIs use `Attributes`, `Settings`
- Google APIs use `config`, `properties`
- Kubernetes uses `spec`, `status`

This pattern is familiar to developers and works well with SDKs and code generation tools.

### 5. Auditability and Intent

Logs and diffs become clearer when business data is grouped:

```json
// Clear audit trail
"client changed policies.password"
"client changed policies.mfaRequired"

// vs unclear flat structure
"top-level password changed"
```

This helps with governance, security reviews, and debugging.

---

## When to Use Flat Payload Structures

Flat structures are appropriate for simple resources with clear, flat domain models:

### Simple CRUD Resources

```json
// User profile - all fields are domain data
{
  "firstName": "John",
  "lastName": "Doe",
  "email": "john.doe@example.com",
  "isActive": true
}
```

### Resources with No Metadata

When there are no control flags or metadata properties needed:

```json
// Simple configuration
{
  "theme": "dark",
  "language": "en",
  "notifications": true
}
```

---

## Design Guidelines

### Use Nested Objects When:

| Condition | Example | Pattern |
|-----------|---------|---------|
| Resource has metadata | `inherited`, `dryRun`, `etag` | `{ "inherited": false, "data": { ... } }` |
| Multiple domain categories | Settings + Policies + Rules | `{ "settings": {}, "policies": {}, "rules": {} }` |
| Future extensibility needed | May add request controls later | `{ "domainObject": { ... } }` |
| Complex business objects | Multi-field configurations | `{ "authentication": { "mfa": {}, "password": {} } }` |

### Use Flat Structures When:

| Condition | Example | Pattern |
|-----------|---------|---------|
| Simple domain model | User profiles, basic settings | `{ "name": "...", "value": "..." }` |
| No metadata needed | Pure data transfer | `{ "field1": "...", "field2": "..." }` |
| Consistent with existing APIs | Don't break established patterns | Follow team/service conventions |

---

## Common Nested Patterns

### Configuration Resources

```json
{
  "inherited": false,
  "enabled": true,
  "config": {
    "timeout": 30,
    "retries": 3,
    "endpoints": ["..."]
  }
}
```

### Settings Resources

```json
{
  "inherited": true,
  "version": "1.0",
  "settings": {
    "theme": "dark",
    "language": "en",
    "features": ["feature1", "feature2"]
  }
}
```

### Policy Resources

```json
{
  "inherited": false,
  "effectiveDate": "2025-01-01",
  "policies": {
    "access": "RESTRICTED",
    "approval": "REQUIRED",
    "audit": "ENABLED"
  }
}
```

---

## Validation and Error Handling

Nested structures allow for more precise validation:

```json
// Error response for nested structure
{
  "error": {
    "code": "INVALID_FIELD",
    "message": "Invalid policy configuration"
  }
}
```

---

## Summary

| Aspect | Nested Structure | Flat Structure |
|--------|------------------|----------------|
| **Best for** | Complex resources with metadata | Simple domain models |
| **Extensibility** | High - separate concerns | Limited - mixed concerns |
| **Validation** | Precise - by object path | Flat - field level only |
| **Audit trail** | Clear - object.field paths | Less clear - flat fields |
| **Partial updates** | Clean - object-level patches | Risky - field conflicts |
| **API consistency** | Follows wrapper object pattern | Simple CRUD pattern |

**Default recommendation**: Use nested structures for resources that have metadata or may evolve in complexity. Use flat structures only for simple, stable domain models with no metadata requirements.