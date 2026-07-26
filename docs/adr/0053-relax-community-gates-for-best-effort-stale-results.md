# Relax Community Report Gates for Best-Effort Stale Results

On active repositories under continuous change, `search_global` perpetually blocked community results behind two sequential all-or-nothing gates. This ADR relaxes both so that entity-targeting can serve whatever query-relevant community reports are already committed — accepting one-detection-cycle staleness — instead of falling back to chunk search on every query.

## Context

`RAGPipeline.search_global` (in `vectors/rag.py`) gates community synthesis behind two checks:

- **Gate 1** (~line 1983): `if is_dirty or not committed_build_id` bails *before* entity targeting. `is_dirty` is true whenever `graph_version != communities_version` OR `committed_build_id IS NULL` — i.e. any file has been indexed since the last committed detection build, or no build has ever committed.
- **Gate 2** (~line 1883, inside `_try_entity_targeting`): `all_points_exist(community_ids=targeted_list)` bails when *any* targeted community report is not yet committed to Qdrant.

For a repo under constant updates, `is_dirty` is nearly always true, so Gate 1 short-circuits to the chunk fallback perpetually — even though:

- Entity targeting can identify query-relevant communities from the committed generation without waiting for the newer detection to settle (ADR-0009–0021).
- Community reports are generated lazily per targeted cluster, not full-root (ADR-0014).
- Some targeted community reports *are* already committed and searchable via `QdrantCommunities.search_filtered`, which returns whatever matches without requiring the full set.

The staleness this introduces: results reflect the entity graph and community membership as of the last committed detection build, which may lag HEAD by some number of file changes. For a semantic-search assistant this is almost always acceptable; for a caller making decisions where one-cycle lag matters (e.g. trading), it is not — hence staleness is signalled explicitly and a future opt-in freshness bound is recommended.

## Decision

**Relax Gate 1.** Remove `is_dirty` from the hard gate; require only `committed_build_id is not None` (there must be at least one prior completed detection build). When `is_dirty`, still `schedule_detection(root_id)` to converge the newer build, but allow targeting to proceed against `(communities_version, committed_build_id)` from the prior committed build. `get_committed_generation` reads the committed pair from the `meta` table directly, so it returns the last-known generation regardless of current dirtiness.

Guard `communities_version is not None` immediately after Gate 1 passes — if `committed_build_id` is non-None but `communities_version` is somehow None (a misconfiguration in the meta table). Rather than a bare `assert` (which raises an unstructured `AssertionError`), replace it with a structured error return for graceful degradation: `{'success': False, 'error': {'code': 'meta_integrity_error', ...}}`, so callers receive a graceful response instead of an exception. (In practice `communities_version` is `INTEGER NOT NULL` in SQLite and should never be None once `committed_build_id` is set; the structured return is defensive.)

**Relax Gate 2.** Replace the `all_points_exist` all-or-nothing check with a best-effort `search_filtered` over `targeted_list`. Pass `is_dirty` (derived in `search_global` and threaded into `_try_entity_targeting`) to determine the correct response mode:

- If `search_filtered` returns 1+ reports:
  - Synthesize them (same synthesis logic as the full-search path).
  - Return `mode="rebuilding"` + `incomplete=true` when `is_dirty=True` (a newer detection build is in progress).
  - Return `mode="ready"` + `incomplete=true` when `is_dirty=False` (all targeted reports are not yet fresh, but the graph is settled — partial coverage only).
- If `search_filtered` returns an empty list (including on its internal error path — `QdrantCommunities.search_filtered` catches all Qdrant exceptions internally and returns `[]`):
  - When `is_dirty=True`: return a root-scoped chunk fallback explicitly from `_try_entity_targeting` — `mode="rebuilding"`, `incomplete=true`, `base_dirs=[root_id]`. Do NOT return None, as that would fall through to `_reports_coverage` and potentially full community search with no `rebuilding` signal.
  - When `is_dirty=False`: return `None` from `_try_entity_targeting` so the caller falls through to the full community-search path, which can scan all committed reports and surface relevant ones outside the targeted set.

**Full-search fallback stays strict.** The post-targeting path (~line 2008) that checks `_reports_coverage` and bails on `coverage == "rebuilding"` is unchanged. Targeting gets staleness tolerance because it is the optimization for active repos; the full-search fallback can afford to wait for reports to settle, and chunk search is fast enough when targeting exits with no match.

## Response semantics

The `mode` field now carries a precise signal:

- `mode="ready"` — the settled graph has been consulted; results are from the committed generation.
- `mode="rebuilding"` — a newer detection build is running; results are from the prior committed generation (stale by one cycle) or from chunk fallback.

`incomplete=true` applies to the **targeting paths only** and indicates partial coverage: not all targeted community reports exist yet, or chunk fallback was used instead. The no-prior-build branch (`not committed_build_id` → `_search_global_fallback`) does not emit `incomplete` — that branch has no partial results to qualify. `graph_version` in the envelope carries `communities_version` — the committed detection-build version the results reflect. Clients that need to compute actual staleness should compare this value to the current `graph_version` obtained from a separate status call; including both fields in the response is deferred to a future enhancement.

No new response fields are introduced by this ADR.

## Consequences

**Positive**
- Active repos serve community results immediately after the first detection build, even under constant churn, instead of perpetually falling back to chunks.
- Non-dirty repos with partial targeted-report coverage still reach the full-search fallback when no targeted reports match, preserving existing quality.
- Targeting keeps its O(relevant) cost profile by serving the committed generation while a newer one builds — no O(N) full-build stall per query.
- Reuses the `incomplete: true` flag already in the response schema; no schema change.

**Negative / accepted trade-offs**
- Community membership and reports may lag HEAD by one detection cycle when `is_dirty=True`. Signalled via `mode="rebuilding"` + `incomplete=true`.
- `graph_version` in the response envelope holds `communities_version` (committed generation), not the current `graph_version`. Clients needing staleness computation must issue a separate status call. Including both fields is deferred.
- Callers needing freshness guarantees have no enforcement yet; a `max_staleness_seconds` opt-in is recommended as follow-up but explicitly deferred.
- `_try_entity_targeting` signature gains an `is_dirty` parameter and a partial-serve branch, a modest complexity increase localized to one method.
- One-cycle TOCTOU window on `is_dirty`: `is_dirty` is computed once at `search_global` entry; if detection commits a new generation during the targeting call, `mode="rebuilding"` may be returned for a graph that has since settled. This is a known limitation, not a bug — the signal is at worst one cycle pessimistic.

## Implementation notes
- One integrated commit: Gate 1 + Gate 2 + partial synthesis are interdependent (Gate 2's partial-serve is only reachable once Gate 1 stops short-circuiting).
- Thread `is_dirty` from `search_global` (~line 1975) into `_try_entity_targeting` as an additional parameter. Update the call site at ~line 1994.
- **Gate 1 block splits into two distinct branches** (replacing the previous single `if is_dirty or not committed_build_id: self.schedule_detection(root_id)` block):
  1. `if not committed_build_id: self.schedule_detection(root_id); return await _rebuilding(...)` — hard gate, no prior build; schedule detection and return immediately with a rebuilding response.
  2. `if is_dirty: self.schedule_detection(root_id)` — no `return`; proceed to entity targeting with the committed generation. Without the explicit no-return here, the dirty-but-committed case never triggers detection and `is_dirty` stays True indefinitely.
- After Gate 1 passes (i.e., `committed_build_id is not None`), guard `communities_version is not None` with a structured error return rather than a bare assert (see Decision section).
- Before the cap comparison at rag.py:1861, intersect `targeted_community_ids` with `set(all_community_ids)` (committed-build IDs only): `targeted_community_ids = targeted_community_ids & set(all_community_ids)`. Without this, a dirty repo accumulates entity→community rows from both the committed and in-progress detection builds, inflating `len(targeted_community_ids)` relative to the committed-build `total`, causing false cap-exceeded and bypassing targeting before `search_filtered` is ever tried.
- In `_try_entity_targeting`, the `search_filtered` fail-open condition is an **empty list**, not a raised exception — `QdrantCommunities.search_filtered` catches all Qdrant exceptions internally and returns `[]`. A defensive try/except may still be retained but is not the primary error path. The existing `if self._communities is None: return None` guard at rag.py:1881 (immediately before the Qdrant call) must be preserved unchanged — it is a distinct guard and must not be removed or conflated with the try/except handling.
- Tests: update the existing `test_entity_targeting_fallback_respects_root_scope` regression to drive `search_filtered` instead of `all_points_exist`; add a Gate 1 test (dirty graph still runs targeting); add a partial-synthesis test (some targeted reports present, is_dirty=True → `mode="rebuilding"`, `incomplete=true`, synthesis emitted); add a non-dirty partial test (is_dirty=False, zero results → None returned → full-search falls through).
