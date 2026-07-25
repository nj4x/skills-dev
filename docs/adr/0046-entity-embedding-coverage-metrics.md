# ADR-0046: Entity Embedding Coverage Metrics in GraphificationStats

## Status

Approved — implemented (commit 37e007f). Counters are internal-only; `get_graph_stats()` does not
serialize them. Not exposed via any MCP tool surface.

## Context

The `GraphificationStats` dataclass tracked `entities_found` (extracted count) and `entities_embed_failed` (failure count), but had **no visibility** into:
- Whether embedding is enabled (`_qdrant_entities` is None/initialized).
- How many entities were successfully embedded (only failures tracked).
- Total entity scope (extracted entities + edge-stub entities).

This made it impossible to trend the embed-attempt success rate within a running process. Note: the
original motivating question ("What is our embedding coverage for this file?") is not actually
answerable with these counters, since they are per-root cumulative. See Decision for the corrected
semantics.

## Decision

Add three fields to `GraphificationStats`, updated during `_extract_and_merge()`:

```python
@dataclass
class GraphificationStats:
    entity_embedding_enabled: bool = False  # _qdrant_entities is not None
    entities_embedded: int = 0              # successful upserts (entities + stubs)
    entities_total: int = 0                 # len(entity_map.entities) + len(stubs), accumulated per file
    # ... existing fields ...
```

- `entity_embedding_enabled`: set to `True` when `_qdrant_entities` is not None **and**
  `entity_map.entities` is non-empty. It is therefore an "embedding actually ran for this file"
  flag, not the "embedding is configured" flag its name suggests. The inline comment in `rag.py`
  currently says `# whether _qdrant_entities is initialized`, which is incomplete; see Consequences
  for the documented stale comment caveat.
- `entities_embedded`: incremented (`+=`) for each successful entity/stub upsert (independent
  counter, not derived from the failure count). Accumulated monotonically per root for the process
  lifetime — not reset between files or re-indexes.
- `entities_total`: `len(entity_map.entities) + len(stubs)` accumulated per file, also monotonically
  (`+=`). Counts upsert _attempts_, not distinct entities: if the same entity appears in multiple
  files (multi-source), it is counted once per file processing pass; if the same file is re-indexed
  N times, it is counted N times. Pre-existing SQLite stubs (inserted before this ADR) are not in
  the `stubs` return value and are not counted.

The ratio `entities_embedded / entities_total` is a per-root, per-process-lifetime embed-attempt
success rate — **not** a per-file coverage fraction and **not** a corpus-wide coverage snapshot.
After restart, it reads 0/0 even if Qdrant holds millions of valid entity points. A re-indexed file
adds to both numerator and denominator regardless of whether its vectors already existed.

## Scope

The counters are updated in **exactly one** call path: `RAGPipeline._extract_and_merge()`.

Not wired:
- `extract_entities_from_file()` (`vectors/rag.py`) performs extraction and graph merge without
  touching any of these counters, so entities indexed through it are invisible to coverage.
- Both stats-update branches in `_extract_and_merge` (the failure branch and the all-succeeded
  branch) are additionally gated on `entity_map.entities` being truthy. A file yielding zero
  entities but non-empty edges creates stubs in SQLite that are counted in neither
  `entities_total` nor `entities_embedded`.

Because `entity_embedding_enabled` stays `False` for a zero-entity file, a consumer cannot
distinguish **"entity embedding is disabled/unconfigured"** from **"this file produced no
entities"** — both present identically.

## Consequences

⚠️ **Internal only, not queryable**: the three fields live on the `GraphificationStats` dataclass
but `get_graph_stats()` does not serialize them — it emits 11 keys including `entities_found` and
`entities_embed_failed` but not the three new counters (rag.py:1361-1372). No MCP tool surface
exposes coverage; the values are reachable only by in-process inspection. The original "explicit
and queryable" claim was false.
⚠️ **Per-process and volatile**: counters are in-memory, reset to zero on server restart, and are
never reconciled against Qdrant. After a restart, coverage reads as 0/0 while any real gap in
Qdrant persists — so a low `entities_embedded` means "little embedded since boot", not "little
embedded overall".
✅ **Per-file accumulation**: counters update as each extraction completes, so within a single
process lifetime the trend is observable in real time.
⚠️ **Partial failure visibility**: the gap between `entities_total` and `entities_embedded`
highlights embedding failures **for the wired path only**, and cannot reveal vectors lost after
upsert — notably those deleted by the stale-cleanup defect in [[0044-stale-entity-vectors-cleanup]],
which are counted as successfully embedded.
⚠️ **`files_pending_extraction` leaks on cancellation**: adjacent to these counters,
`files_pending_extraction` is incremented before the try block and decremented only in the success
path and in `except Exception`. `asyncio.CancelledError` is a `BaseException`, so cancelling at any
await point permanently inflates the gauge for that root; there is no `finally`.
✅ **No performance cost**: counters are simple integer increments in the embedding loop.
⚠️ **No test coverage**: no test references `entities_embedded`, `entities_total`, or
`entity_embedding_enabled`. The existing suite passes without exercising any of this behavior.
⚠️ **`entity_embedding_enabled` field comment contradicts documented semantics**: the field's inline
comment in `rag.py` says `# whether _qdrant_entities is initialized`, but the actual behavior (set
only when `entity_map.entities` is truthy AND `_qdrant_entities` is not None) is what the Decision
section documents. The code comment is stale.

## Alternatives considered

- **Expose counters via `get_graph_stats()`**: serialize the three fields in `get_graph_stats()` and
  expose through the MCP surface so coverage is observable externally. Deferred — the counters are
  per-process and would show only partial data after restart, which could mislead callers; a
  persistent coverage store would be needed for meaningful external exposure.
- **Rename `entity_embedding_enabled` to `entity_embedding_ran`**: Deferred. `entity_embedding_ran`
  better describes the actual semantics (set only when embedding has executed, not merely configured),
  and past tense makes explicit that the field is retrospective. Not yet adopted to avoid churn;
  would be bundled with a prospective external-exposure change to `get_graph_stats()`.
- **Derive `entities_embedded` as `entities_total − entities_embed_failed`**: simpler, no extra
  counter. Rejected because the two closures count against a shared `embed_failures` variable but
  the denominator logic differs per branch; an independent counter is unambiguous.

## Related

- [[0043-entity-identity-centralization]]: used for consistent entity identity.
- [[0045-edge-stub-entity-embedding]]: stubs included in `entities_total` and `entities_embedded`.
- [[0044-stale-entity-vectors-cleanup]]: vectors deleted by the cleanup defect are counted as
  successfully embedded in `entities_embedded` — the gap between `entities_total` and
  `entities_embedded` therefore understates the actual coverage deficit.
