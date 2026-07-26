# Consolidate 16 Tools into 3 Core Operations (index, search, cleanup)

The mcp-vectors tool surface had grown to 16 exposed tools, making routing harder for the LLM. This ADR consolidates the surface to **3 exposed tools** — `index_codebase`, `search_root`, and `clear_index` — mapping onto three core operations: index, search, and cleanup.

All 14 other tools are unregistered (decorators removed; bodies kept temporarily pending deletion):

- **Eight utility tools:** `audit_indexed_secrets`, `get_community_report`, `get_indexing_status`, `get_stats`, `index_files`, `list_communities`, `list_indexed_files`, `purge_indexed_secret_files`.
- **Two graph-traversal tools:** `get_entity_callers`, `get_entity_neighbors`.
- **Four search tools:** `search_code`, `search_documents`, `search_entities`, `search_global`.

Secret-remediation tools (`audit_indexed_secrets`, `purge_indexed_secret_files`) are removed intentionally. Secret remediation is now out-of-band; these tools were unused and their removal is deliberate.

`search_root` **replaces all four search tools** and absorbs the graph-traversal tools. It is the single entry point for retrieval. Internally it fans out across three channels — `chunks`, `entities`, `communities` — where `chunks` handles all text and code retrieval (collapsing the former `search_documents` and `search_code` into one), and the `entities` and `communities` channels reuse the logic formerly exposed as `search_entities`, `search_global`, `get_entity_callers`, and `get_entity_neighbors`. None of those four remain as standalone tools; they are now internal channels of `search_root`. This is a true consolidation from 16 → 3, not a partial reduction. Not for exact symbol/string lookups — use ripgrep/fd instead.

## Behavior of `search_root`

`search_root` takes `query`, `root_path`, `limit` (bounded `ge=1, le=100`, matching the tightest existing bound), and `min_score`. It dispatches all three channel searches in parallel with a unified timeout (`SEARCH_ROOT_TIMEOUT_SECONDS`, default 60s). Results are returned per-channel, each with a `success` boolean and optional `error` field. Per-channel metrics are recorded alongside a top-level `search_root` entry to preserve engagement trend visibility from ADR-0005.

- **Query validation:** the query is stripped and checked — `if not query.strip()` returns a top-level error without dispatching any channel.
- **`root_path` validation:** before constructing channel tasks, `search_root` validates `root_path`: if empty or resolution fails (e.g., relative path, non-existent root), return immediately with `{"success": false, "error": {"code": "invalid_root_path", "message": "..."}}` without dispatching channels. This is consistent with how `index_codebase` handles invalid paths (server.py:862-864).
- **`limit` bounds:** `limit` is bounded [1, 100]; the maximum result envelope is 3×limit (up to 300 total entries).
- **No pre-flight indexing check:** there is no pre-flight `get_indexing_status` call. Channels are dispatched immediately; if the root is not indexed, each channel fails with its own per-channel error. This keeps the common path fast and avoids the overhead of a Qdrant scroll audit on every call.
- **Aggregate success rule:** top-level `success: true` if **at least one channel succeeds**; `success: false` only if all three channels fail.
- **`chunks` channel scope:** this channel is **root-scoped** and covers both text documents and code files. It passes the root via `base_dirs=[root_path]` to `pipeline.search()`. This uses a Python post-filter (after a 5× overscan of results) rather than the indexed `root_id` Qdrant filter path. The trade-offs are accepted: no per-root confidence score (ADR-0042) and a 5× scan overhead — accepted in exchange for a simpler dispatch contract that does not require `root_id` pre-computation. The former `search_documents` and `search_code` are both subsumed here. There is no longer a cross-root document search on the tool surface.
- **`limit` semantics:** `limit` applies **independently per channel**, not as a global cap across channels. The maximum-result envelope is therefore up to **3×limit** total (one `limit`-sized page per channel). This reconciles the previously divergent defaults (`search_code`=10, `search_documents`=15, `search_global`=5) under one uniform value.
- **`entities` channel — two-step fan-out:** the `entities` channel performs a two-step operation: (1) semantic entity search via `pipeline.search_entities_semantic(root_path, query, limit)`, which returns a list of entities ranked by relevance, bounded by `limit` — `limit` controls the size of the returned `results` list, not the enrichment sub-arrays; (2) for each of the top-N matched entities (where N = `ENTITY_ENRICH_LIMIT = min(limit, 5)`), `pipeline.get_callers()` and `pipeline.get_neighbors()` are fetched in parallel via `run_in_executor` so that sync SQLite calls do not block the event loop. `pipeline.get_neighbors()` returns a dict with a `'neighbors'` key; the channel extracts `result['neighbors']` (a list) before attaching to the enriched entity record. The channel result is a list of matched entities, each with `callers` (list) and `neighbors` (list) sub-arrays. Callers and neighbors are fetched only for the top N matched entities to prevent unbounded enrichment fan-out; N defaults to `min(limit, 5)`. If enrichment (`get_callers`/`get_neighbors`) raises for a specific entity, that entity's enrichment fails gracefully — callers and neighbors for that entity are empty, but the entity is still returned. The enrichment exception is logged but does not fail the entire entities channel. This subsumes `get_entity_callers` and `get_entity_neighbors` without requiring a named entity as input — the query string drives entity discovery, then graph data is attached automatically.
- **`ENTITY_EXTRACTION=false` guards:** the `entities` and `communities` channel functions each open with an explicit guard — `if not ENTITY_EXTRACTION: return {"success": True, "results": [], "warning": "ENTITY_EXTRACTION disabled"}` — before any other logic. (`ENTITY_EXTRACTION` is the bare module-level bool imported from `vectors.rag`, not a settings object.) This is a proactive return, not a try/except reshape of a downstream RuntimeError. The call still succeeds overall because the `chunks` channel carries it.

### Timeout and partial-result strategy

Channel tasks are harvested with `asyncio.wait(tasks, timeout=SEARCH_ROOT_TIMEOUT_SECONDS)`:

- Completed channels return their results. Each done task's result must be extracted inside a try/except — `try: result = task.result() except Exception as e: channel_result = {"success": False, "error": str(e)}` — so exception-raising done tasks are shaped as per-channel failures, not re-raised.
- Pending channels are cancelled via `task.cancel()` followed by `asyncio.gather(*pending, return_exceptions=True)` to drain cancellations cleanly.
- Each timed-out channel is reported as `{"success": false, "error": "timeout"}`.

Partial results are delivered: a slow or failed channel never blocks or discards the channels that completed.

`SEARCH_ROOT_TIMEOUT_SECONDS` must be added to `vectors/config.py` as a new field (default 60, validated > 0 at startup; zero or negative values default to 60).

## Considered Options

- **Keep all tools separate** — rejected because routing logic was pushed onto the LLM; the four search tools have divergent contracts that the LLM must reason about before each call.
- **Env-flag to hide tools** — rejected because this is a one-way migration. Unregistering by removing the `@_tool()` decorator is cleaner; the eventual deletion is just removing dead code.
- **Deprecation shim (alias old names to `search_root`)** — rejected because usage is internal (Claude Code only); a hard break plus changelog entry is sufficient.
- **Flat merged result list** — rejected in favor of per-channel keys because each channel has a different result shape; flattening obscures that and forces the LLM to re-type-narrow.
- **Retain `search_entities`/`search_global`/`search_documents` as standalone tools alongside `search_root`** — rejected. Keeping them would make the change net-additive (add `search_root`, remove only `search_code`) rather than a real consolidation, and would leave the LLM with overlapping routing choices. The single-channel targeting they offered is subsumed by `search_root`'s per-channel results.
- **Lazy channel dispatch** — skip or defer heavy channels (communities) when chunks return strong results. Rejected: eager dispatch keeps the contract simple; the design opts for consistency (always run all three) over per-call optimization. Communities rebuilding and enrichment latency are acceptable tradeoffs for a unified interface.
- **Internal async complexity as a simplicity violation** — rejected concern. The design goal is user-facing simplicity (one tool instead of many). Internal async fan-out and two-step entity enrichment are implementation details that do not affect the tool surface.
- **Dropped filter parameters** — `extensions`, `file_types`, `exclude_files`, `include_full_chunks`, `max_chunk_chars`, `base_dirs`, `max_chunks_per_file`, and `include_metadata` are not threaded to per-channel dispatchers. Rationale: the simplified 4-parameter surface (`query`, `root_path`, `limit`, `min_score`) is the design goal; these filters can be added to individual channel sub-params later if needed.

## Implementation Requirements

Implement `pipeline.search_entities_semantic(root_path: str, query: str, limit: int) -> List[EntityMatch]` in `vectors/rag.py`. This method performs semantic ANN search over entity embeddings (via `self._qdrant_entities.search()`) with a fallback to substring matching (`self.find_entities()`) when embeddings are unavailable. The method is called by the entities channel to discover relevant entities before enrichment.

## Consequences

- The **three** remaining exposed tools are: `index_codebase`, `search_root`, `clear_index`. Every other tool is unregistered.
- Loss of a dedicated cross-root document search: the `chunks` channel is root-scoped. If cross-root document search is needed later, it must be reintroduced explicitly.
- Secret remediation is now out-of-band. `audit_indexed_secrets` and `purge_indexed_secret_files` were unused; their removal is intentional.
- The former `get_indexing_status` safe-workflow first step is no longer part of the search flow. `search_root` dispatches channels immediately; unindexed roots surface as per-channel failures. Callers that need to verify index state before searching must call `index_codebase(dry_run=true)`, which returns status without indexing.
- The graph-traversal capabilities (`get_entity_callers`, `get_entity_neighbors`) are no longer directly callable. Callers and neighbors for semantically relevant entities are now accessible via the `entities` channel's two-step fan-out: the channel returns a list of matched entities, each enriched with `callers` and `neighbors` sub-arrays. This is not a capability loss; callers+neighbors are returned for semantically relevant entities rather than requiring a specific named entity as input.
- The maximum result envelope is 3×limit (one limit-sized page per channel); callers should set limit accordingly.
- ADR-0005 parity test must be updated:
  - Delete all four graph/entity-tool pre-conditions from CLAUDE.md (`get_entity_callers`, `get_entity_neighbors`, `search_entities`, `search_global`) — those tools are unregistered. This deletion is what fixes `test_no_orphaned_tool_names_in_claude_md` (that test scans CLAUDE.md directly for references to registered tools).
  - Add a single `search_root` pre-condition entry to CLAUDE.md with trigger-first framing: "Use this when you need to search a codebase root semantically, by entity name, and architecturally all at once. Not for exact symbol/string literals — use ripgrep/fd instead; not for cross-root document search — use index_codebase to add other roots."
  - Update `TARGETED_TOOLS` in `mcp/mcp-vectors/tests/`: remove the four old search/graph entries and add `search_root`, so `TARGETED_TOOLS = frozenset({'search_root'})`. This preserves the parity enforcement tests that verify no tool is reachable outside the targeted set.
- The FastMCP server instructions preamble (server.py lines 482–501) must be rewritten to describe the new 3-tool surface and the internal-channel model of `search_root`. The `search_root` docstring must include a "Not for exact symbol/string lookups — use ripgrep/fd instead" contrast so the LLM does not route exact-match queries through it.
- Documentation that references now-unregistered tools must be updated: `docs/agents/search-strategy.md`, root `README.md`, and `mcp/mcp-vectors/README.md` all mention `search_code`, `search_documents`, `search_entities`, `search_global`, `get_entity_callers`, `get_entity_neighbors`, and/or other removed tools and must be revised to reflect the 3-tool surface.
