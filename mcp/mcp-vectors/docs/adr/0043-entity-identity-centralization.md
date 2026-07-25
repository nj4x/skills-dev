# ADR-0043: Centralize Entity Identity Formula

## Status

Approved

## Context

The entity identity formula `SHA256(name.lower() | type | root_id)` is defined in three places across the codebase:
1. `graph_store.py:_entity_id()` — canonical definition
2. `entity_extractor.py:_merge_entities()` — inline sha256 with raw `entity.type` (no coercion)
3. `rag.py` — imports private `_entity_id` from graph_store

This creates two problems:
- **Inconsistent type coercion**: `entity.type` can be `None`, producing digest `"None"` in extractor, while rag.py uses `getattr(e,'type','') or ""` → `""`. Same-name/different-type entities collide.
- **Seam leakage**: `_entity_id` is private but imported across modules, making it fragile.

## Decision

Centralize the formula in `graph_store.py` as a **public** function `entity_id()` with **mandatory type normalization** baked in:

```python
def entity_id(name: str, type_: str, root_id: str) -> str:
    type_normalized = (type_ or "").strip().lower()
    return hashlib.sha256(f"{name.lower()}|{type_normalized}|{root_id}".encode()).hexdigest()
```

- `type_` coercion: `(type_ or "").strip().lower()` handles `None`, whitespace, and case-folding in one place.
- Replace inline sha256 in `entity_extractor._merge_entities()` with a call to `entity_id()`.
- Update `rag.py` to import the public name.
- Add backward-compat aliases `_entity_id` and `_edge_id` for migration.

## Consequences

✅ **Single source of truth**: type normalization is centralized and mandatory.
✅ **No orphans**: consistent identity across extraction, graph storage, and embedding.
✅ **Public API**: no more private imports; cleaner module boundaries.
⚠️ **Migration effort**: all call sites and tests must update imports (automated via sed; fully reversible).

## Related

- [[0044-stale-entity-vectors-cleanup]]: depends on centralized identity for deletion targeting.
- [[0045-edge-stub-embedding]]: depends on consistent identity for stub creation.
