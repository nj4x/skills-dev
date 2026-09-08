# Path Structure Guidelines

This document defines how to organize API paths to separate concerns and maintain modularity.

---

## Separate Paths for Independent Features

**Even if features are related in policy, keep API paths separate if they are technically independent.**

### Example: Federated Authentication vs Directory Sync

These features may be related by policy but are technically independent:

- ✅ `/federated-auth-configurations`
- ✅ `/directory-sync-configurations`

**Avoid combining them:**

- ❌ `/federation/auth-config`
- ❌ `/federation/directory-sync`

### Benefits

- **Modularity**: Each feature can evolve independently
- **Scalability**: Features can be scaled or deprecated separately
- **Maintainability**: Changes to one feature don't affect the other
- **Clarity**: API consumers understand what each endpoint manages

---

## Separate Configuration from Runtime Operations

**Do not mix configuration setup APIs with APIs that execute operations.**

### Configuration APIs

Configuration APIs manage setup and settings. They typically:
- Use CRUD operations on configuration resources
- Are called during setup/admin flows
- Change infrequently

Examples:
```
GET  /federated-auth-configurations
POST /federated-auth-configurations
GET  /federated-auth-configurations/{id}
PATCH /federated-auth-configurations/{id}
DELETE /federated-auth-configurations/{id}

GET  /directory-sync-configurations
POST /directory-sync-configurations
```

### Runtime/Operational APIs

Runtime APIs execute actions or handle real-time flows. They typically:
- Are called during user flows
- Process callbacks or webhooks
- Perform synchronization or authentication actions

Examples:
```
POST /federated-auth/callback
POST /federated-auth/logout
POST /scim/Users
POST /scim/Groups
POST /directory-sync/trigger
```

### Path Pattern

| Type | Pattern | Examples |
|------|---------|----------|
| Configuration | `/[feature]-configurations` | `/federated-auth-configurations`, `/webhook-configurations` |
| Runtime | `/[feature]/[action]` or `/[protocol]/[resource]` | `/federated-auth/callback`, `/scim/Users` |

---

## Summary

| Principle | Avoid | Use |
|-----------|-------|-----|
| Feature separation | `/federation/auth`, `/federation/sync` | `/federated-auth-*`, `/directory-sync-*` |
| Config vs Runtime | `/federated-auth` (mixed) | `/federated-auth-configurations` + `/federated-auth/callback` |