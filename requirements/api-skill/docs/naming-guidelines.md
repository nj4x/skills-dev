# Naming Guidelines

This document defines naming conventions for API paths and resources to ensure clarity and consistency.

---

## Avoid Abbreviations Without Context

**Avoid using unclear or unexplained abbreviations in URL paths.**

- ❌ `/fa-config`
- ✅ `/federated-auth-configurations`

Use clear and descriptive resource names to ensure better understanding for all API consumers.

---

## Use Flat, Noun-Based Resource Names

**Favor simple, noun-based resource names. Avoid deep nesting or verb-driven paths.**

### Use

- ✅ `/federated-auth-configurations`
- ✅ `/directory-sync-configurations`
- ✅ `/system-roles`
- ✅ `/user-groups`

### Avoid

- ❌ `/federation/auth/configurations` (deep nesting)
- ❌ `/setupFederatedConnection` (verb-driven)
- ❌ `/systemRoles` (not kebab-case)

Flat structures improve predictability and make APIs easier to document and consume.

---

## Path Naming Format

Use **kebab-case** for URL paths:

- ✅ `/system-roles`, `/user-groups`, `/access-tokens`
- ❌ `/systemRoles`, `/user_groups`, `/accesstokens`

---

## Do Not Use Module Names as URL Root Paths

**Do not expose internal module names like `federation` or `auth` in the API root.**

### Avoid

- ❌ `/federation/mock-idp/authorize`
- ❌ `/auth/sso/callback`

### Use

- ✅ `/mock-idp/authorize`
- ✅ `/sso/callback`

Clients should interact with clearly defined **resources**, not internal implementation details.

---

## Summary

| Rule | Bad Example | Good Example |
|------|-------------|--------------|
| No abbreviations | `/fa-config` | `/federated-auth-configurations` |
| Flat structure | `/federation/auth/config` | `/federated-auth-configurations` |
| No verbs in paths | `/setupConnection` | `/connections` |
| No module roots | `/federation/callback` | `/federated-auth/callback` |
| Use kebab-case | `/systemRoles` | `/system-roles` |