# API Versioning

This document defines the versioning strategy for APIs, including deprecation guidelines.

---

## Checkpoint

> **⚠️ REQUIRED**: When designing APIs, always ask the user:
> - "What is the current API version?"
> - "Are there any deprecated versions that need sunset dates?"

---

## Path-Based Versioning

Include the version in the URL path:

```
/v1/resources   # Deprecated version (if applicable)
/v2/resources   # Current stable version
/v3/resources   # Next version (if applicable)
```

### Version Format

- Use simple integers: `v1`, `v2`, `v3`
- ❌ Avoid: `v1.0`, `v1.1`, `v2-beta`

Minor changes should be backward-compatible within the same major version.

---

## When to Create a New Version

Create a new API version when making **breaking changes**:

| Change Type | Breaking? | New Version? |
|-------------|-----------|--------------|
| Add new optional field | No | No |
| Add new endpoint | No | No |
| Remove a field | Yes | Yes |
| Rename a field | Yes | Yes |
| Change field type | Yes | Yes |
| Change response structure | Yes | Yes |
| Remove an endpoint | Yes | Yes |
| Change authentication method | Yes | Yes |

---

## Deprecation Process

### Step 1: Announce Deprecation

Document the deprecation with a sunset date (minimum 6 months notice recommended).

### Step 2: Add Deprecation Headers

Add these headers to all responses from deprecated endpoints:

```http
Deprecation: true
Sunset: Sat, 01 Jun 2025 00:00:00 GMT
Link: </v2/resources>; rel="successor-version"
```

| Header | Description |
|--------|-------------|
| `Deprecation` | Indicates the API version is deprecated |
| `Sunset` | Date when the version will be removed (RFC 7231 format) |
| `Link` | Points to the replacement version |

### Step 3: Optional Warning in Response Body

Include a warning in the response body:

```json
{
  "data": { ... },
  "_meta": {
    "deprecation": {
      "message": "This API version is deprecated and will be removed on 2025-06-01",
      "sunset": "2025-06-01T00:00:00Z",
      "successor": "/v2/resources"
    }
  }
}
```

### Step 4: Maintain Until Sunset

Continue supporting the deprecated version until the sunset date.

### Step 5: Remove After Sunset

After the sunset date, return 410 Gone:

```json
{
  "error": {
    "code": "VERSION_REMOVED",
    "message": "API v1 was removed on 2025-06-01. Please use /v2/resources"
  }
}
```

---

## Version Documentation

In API documentation, clearly indicate:

| Version | Status | Sunset Date |
|---------|--------|-------------|
| v1 | Deprecated | 2025-06-01 |
| v2 | Current | - |
| v3 | Beta | - |

---

## Migration Guides

When introducing a new version:
1. Document all breaking changes
2. Provide migration guides with examples
3. Offer a migration period with both versions available
4. Communicate timeline to API consumers

---

## Summary

| Aspect | Guideline |
|--------|-----------|
| Format | Path-based versioning (`/v1/`, `/v2/`) |
| When to version | Only for breaking changes |
| Deprecation notice | Minimum 6 months |
| Headers | Use `Deprecation`, `Sunset`, `Link` headers |
| After sunset | Return 410 Gone |