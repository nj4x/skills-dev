# ADR-0043: Centralize Entity Identity Formula

## Status

Approved — implemented (commit 085d9da). Breaking identity change: all pre-existing digests are
invalidated. No migration path or re-index detection exists; a full per-root `clear_index` + re-index
is required.

## Context

The entity identity formula `SHA256(name.lower() | type | root_id)` is defined in three places across the codebase:
1. `graph_store.py:_entity_id()` — canonical definition
2. `entity_extractor.py:_merge_entities()` — inline sha256 with raw `entity.type` (no coercion)
3. `rag.py` — imports private `_entity_id` from graph_store

This creates two problems:
- **Divergent identity across subsystems**: `entity_extractor._merge_entities` hashed `entity.type` verbatim (including `None` as the literal string `"None"`), while rag.py coerced `None→""` before hashing. The same entity thus received different IDs in different layers — its vector was indexed under a digest no SQLite row carried, making it permanently unreachable by entity-graph targeting.
- **Seam leakage**: `_entity_id` is private but imported across modules, making it fragile.

## Decision

Centralize the formula in `graph_store.py` as a **public** function `entity_id()` with **mandatory type normalization** baked in:

```python
def entity_id(name: str, type_: str, root_id: str) -> str:
    type_normalized = (type_ or "").strip().lower()
    return hashlib.sha256(f"{name.lower()}|{type_normalized}|{root_id}".encode()).hexdigest()
```

- `type_` coercion: `(type_ or "").strip().lower()` handles `None`, whitespace, and case-folding of the **type** in one place.
- Replace inline sha256 in `entity_extractor._merge_entities()` with a call to `entity_id()`.
- Update `rag.py` to import the public name.
- The companion edge formula is likewise exposed as public `edge_id()`.

The rename is a **hard cutover**: no backward-compat aliases are provided. `graph_store` defines
only the public `entity_id` and `edge_id`; `_entity_id` / `_edge_id` no longer exist.

## Consequences

✅ **Single source of truth**: type normalization is centralized and mandatory.
✅ **Consistent type handling**: extraction, graph storage, and embedding derive identical IDs for the same (name, type, root).
✅ **Public API**: no more private imports; cleaner module boundaries.
⚠️ **Hard cutover, not a migration**: the private names were removed outright. All production call
sites and tests were migrated in the same commit. Any external caller importing `_entity_id` or
`_edge_id` breaks with `AttributeError`/`ImportError` — there is no deprecation window.
⚠️ **Stale references remain in test prose**: `tests/test_entity_embed_failures.py` still names
`graph_store._entity_id(...)` in its module docstring and a test docstring; the assertions
themselves use the public name. Cosmetic, but misleading when read.
⚠️ **Breaking identity change, not a pure refactor**: the formula adds type lowercasing and
`None`-coercion that were absent in the canonical `_entity_id` definition. Any entity whose type
string was not already lowercase (e.g. `Class`, `FUNCTION`, `None`) has a different digest under the
new formula. Existing SQLite rows and Qdrant vectors indexed before this commit carry stale digests
and become unreachable orphans. A full per-root `clear_index` + re-index is required; no migration
path or re-index detection exists.

## Known limitations (not addressed)

- **Name case-folding collisions**: `entity_id()` lowercases `name`, so `HTTP` and `Http` of the
  same type collapse to one identity while callers persist whatever raw casing arrived first.
  Whichever entity is written last wins the stored display name. This is deliberate (it merges
  casing variants of the same concept) but it is *not* "all identity ambiguity resolved" — real
  distinct entities differing only by case cannot be represented.
- **Empty / whitespace-only names**: no guard exists. A name of `""` or `"   "` yields a stable
  digest and is stored like any other entity; whitespace in names is not stripped (only the type
  is stripped). `"Foo"` and `" Foo"` therefore hash to *different* IDs.
- **No identity versioning**: the digest has no scheme/version prefix, so any future change to the
  formula silently invalidates every previously indexed ID and requires a full re-index. This ADR
  already realized that risk once — the formula changed without a version prefix — which argues for
  a scheme prefix (e.g. `v2|name|type|root`) before any further change.
- **Type case-folding collisions on stored display value**: the `type` column in SQLite persists raw
  casing (`Class`, `class`) while the identity digest uses the lowered value, so `Class` and `class`
  for the same name collapse to one row with last-writer-wins display type.
- **Edge-endpoint type resolution is last-writer-wins**: graph_store.py builds an
  `entity_type_map = {e.name.lower(): e.type}` dict from extracted entities (last entry wins when
  multiple entities share a lowercased name). An edge endpoint is looked up in this map to determine
  its type; if two extracted entities share a lowercased name, the edge gets the last-seen entity's
  type, which may yield a different `entity_id` — mis-attaching the edge or fabricating a spurious
  stub vector.
- **No Unicode normalization or casefolding depth**: names are not NFC/NFD normalized, so visually
  identical names can hash differently. Type case-folding uses Python's `.lower()` which is
  locale-naive and does not match SQL's `LOWER()` for non-ASCII; using `.casefold()` would be
  more robust but still locale-dependent.

## Alternatives considered

- **Deprecation shim** (re-export `_entity_id = entity_id` alongside the new public name): allows
  external callers to migrate incrementally. Rejected — no known external callers exist, and the
  shim adds dead code the project convention prohibits.
- **Normalize types at parse/extraction time** (lowercase before storing in `Entity.type`):
  eliminates the stored/identity casing mismatch at the source. Rejected — requires changes to
  entity extractor and LLM prompt output handling; deferred.
- **Versioned digest prefix** (e.g. `v2:sha256(...)`): would let a future change be detected and
  migrated rather than silently invalidating all existing data. Not implemented; recommended before
  any future formula change.

## Related

- [[0044-stale-entity-vectors-cleanup]]: depends on centralized identity for deletion targeting.
- [[0045-edge-stub-entity-embedding]]: depends on consistent identity for stub creation.
- [[0046-entity-embedding-coverage-metrics]]: exposed via the same graph_store module; shares the
  entity identity and type-coercion assumptions.
