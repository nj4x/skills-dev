# ADR-0045: Embed Edge-Stub Entities into Qdrant

## Status

Approved — implemented (commit 209a8da). Outcome currently negated on re-index by the ADR-0044
defect.

## Context

During entity graph indexing, `replace_file_entity_map()` creates "edge-stub" entities in SQLite for edge endpoints that don't appear in the extracted entity map. These stubs maintain referential integrity but were **never embedded to Qdrant**, creating:
- **Coverage gaps**: Qdrant queries miss stub entities; entity-graph reranking cannot resolve them.
- **Orphaned records**: SQLite has entities with no corresponding Qdrant vectors.
- **Hidden inconsistency**: stats show 100% "embedded" while stubs are silently missing.

**What stubs actually are**: stubs arise from two edge sources with different stub populations:

1. **AST parser (tree-sitter)**: emits `imports` edges with `source = file_path` (an absolute
   filesystem path string) and `target = module_name` (e.g. `"os"`, `"numpy"`). Neither is an
   extracted `Entity`, so both become stubs. The dominant stub population is therefore absolute
   filesystem paths and unqualified module names, embedded as `"<abs path>: (no description)"` and
   `"os: (no description)"`. These inject path and module noise into the entity vector space and
   persist absolute filesystem paths in Qdrant payloads.

2. **LLM relationship extractor**: emits edges whose source/target are semantic entity names that
   may not appear in the extracted entity list. These produce meaningful stubs (domain concept names)
   for which reranking resolution is the intended benefit.

The stated reranking benefit applies to category 2 stubs. Category 1 stubs (the likely majority for
code-heavy roots) dilute the entity vector space with filesystem paths and module strings.

## Decision

Embed edge-stub entities into Qdrant alongside regular entities:

1. **Return stub info from `replace_file_entity_map()`**: return `(version, stubs, deleted_ids)` where stubs are dicts `{"id": eid, "name": name, "type": type}`.
2. **Embed in `_extract_and_merge()`**: after graph update, embed stubs using the same async `_embed_stub()` closure and embedding semaphore as regular entities.
3. **Shared error accumulation**: stub embedding failures increment the same `embed_failures` /
   `embeds_succeeded` counters as regular entities and share the per-signature warning-suppression set.
4. **Empty descriptions**: stubs have `description=""` in SQLite; embedding text is derived from the
   entity name via `_entity_embedding_text(stub_name, None)`, which returns
   `f"{stub_name}: (no description)"`. The stub's type is passed to the Qdrant payload but does not
   appear in the embedded text. Every stub shares the literal suffix `": (no description)"`, which
   reduces inter-stub cosine separation for short names.

Benefits:
- Keeps `GraphStore` synchronous (no async dependency).
- Stubs are embedded with regular entities, using the shared semaphore and failure counters.
- Consistent identity via [[0043-entity-identity-centralization]].

## Scope

Stub embedding is wired in **exactly one** call path: `RAGPipeline._extract_and_merge()`.

Not wired:
- `extract_entities_from_file()` (`vectors/rag.py`) calls `replace_file_entity_map` and discards the
  returned stub list — stubs created on that path are never embedded.
  Note: `extract_entities_from_file` currently has no callers anywhere in the repository (no MCP
  tool, no test invokes it directly); the coverage gap is latent rather than active. If this method
  is not intended to be reachable it should be removed rather than documented as an unwired path.
- `GraphStore.merge_entity_map()` discards stubs by design (returns only `graph_version`).

Additionally, within `_extract_and_merge` the whole embedding block is gated on
`entity_map.entities` being truthy. `replace_file_entity_map` creates stubs **unconditionally**, so
a file that yields zero entities but non-empty edges produces stubs in SQLite that are never
embedded — the gate short-circuits before the stub loop is reached.

## Alternatives considered

- **Lazy / on-demand stub embedding** (embed a stub the first time a query needs to resolve it, or
  in a background backfill pass): avoids paying embedding cost for stubs that are never queried and
  avoids re-embedding on every re-index. Rejected for implementation simplicity and to keep
  read paths free of write-side latency, at the cost of a permanent coverage gap between write and
  first read.
- **Batch stub embedding in a separate sweep** (collect stubs across files, embed once per root
  after indexing settles): amortizes cost properly and would sidestep the re-creation churn.
  Rejected as extra machinery for the first iteration.
- **Do not embed stubs; mark them non-embeddable in SQLite**: honest about the gap and zero cost,
  but leaves entity-graph reranking unable to resolve edge endpoints — the problem this ADR exists
  to solve.
- **Named return type** (a `FileMergeResult` dataclass rather than a raw 3-tuple): would give the
  three return values stable names and prevent silent positional-mismatch bugs. Rejected for
  simplicity in the initial iteration; the 3-tuple is consumed by exactly one caller
  (`_extract_and_merge`), and two other call sites discard the extras — a dataclass would add a new
  type with no immediate benefit at those discarding sites.

## Consequences

⚠️ **Coverage improved, not complete**: stubs are embedded only for files processed through
`_extract_and_merge` **and** only when that file also yielded at least one extracted entity. Files
processed via `extract_entities_from_file`, and zero-entity/non-empty-edge files, still leave SQLite
entities with no Qdrant vector.
⚠️ **Inconsistent error tracking**: `seen_sigs` is a single set shared by the `_embed_entity` and
`_embed_stub` closures. A stub failure whose exception type was already logged for a regular entity
is silently suppressed — the counter increments but no warning is emitted, so a stub-specific
failure mode can be completely invisible. The two handlers also diverge: `_embed_entity` logs with
`exc_info=True` plus an attribute dump of the entity, while `_embed_stub` logs with `exc_info=exc`
and no attribute detail.
⚠️ **Reranking reach limited by embedding quality**: for the wired path, entity-graph reranking can
resolve edge-endpoint names that previously had no vector. However, because every stub embeds
`"{name}: (no description)"` with an identical suffix, short stub names have compressed cosine
separation and may not be distinguished reliably from each other by semantic search.
⚠️ **Recurring LM cost, not amortized**: `_purge_file_contributions` deletes stubs whose sole source
was the file and `replace_file_entity_map` re-creates them, so every re-index of a file re-embeds
its stubs from scratch. The cost is per-re-index, not one-time.
⚠️ **Interacts with the ADR-0044 defect**: because stale-vector deletion runs *after* the stub
upserts and `deleted_ids` includes the just-re-created stub IDs, re-indexing currently deletes the
stub vectors this ADR writes. See [[0044-stale-entity-vectors-cleanup]] "Known defect".
⚠️ **No test coverage**: no test drives non-empty stubs through `_extract_and_merge` or asserts that
stub vectors are upserted.

## Related

- [[0009-entity-embeddings-in-qdrant]]: established the embedding-at-extraction-time contract this
  ADR extends to stubs; defines the collection and embedding-text format this ADR relies on.
- [[0011-entity-search-scope-and-fallback]]: K=20 retrieval with 30% community cap — category-1
  stubs (file paths, module names) consume this budget and may increase cap-trigger and zero-match
  rates at search_global time. Whether stubs receive community assignments is not stated.
- [[0012-mcp-vectors-entities-qdrant-collection]]: defines the entity collection schema; stubs are
  upserted there with `description=""` in the payload.
- [[0043-entity-identity-centralization]]: stub IDs computed using centralized formula.
- [[0044-stale-entity-vectors-cleanup]]: stub IDs are in `deleted_ids`; the delete-after-upsert
  defect means 0044 currently deletes the freshly re-created stub vectors this ADR writes, inverting
  the intended interaction. The combined effect on re-index is a net loss of all single-file vectors.
- [[0046-entity-embedding-coverage-metrics]]: stubs included in `entities_total` count.
