# Store Entity Embeddings in Qdrant for Targeted Community Summarization

## Context

ADR-0004 made community report generation lazy: the first call to `search_global` triggers `generate_all_reports` — one LLM call per detected cluster — across every community in the root. Subsequent calls hit the cache. The problem is **first-query latency**: for a root with many communities, the caller stalls while all N communities are summarized in batch, even if the query is only relevant to 2–3 of them.

Entities are already extracted eagerly during indexing (background task in `_extract_and_merge`). Each entity has a `description` field populated by the LLM extractor and stored in the SQLite graph store. These descriptions are available at extraction time with no additional LLM cost.

Community report generation is expensive specifically because it requires LLM synthesis of cluster content. The cluster-to-query relevance question — *which communities does this request care about?* — could be answered cheaply if entities were searchable by semantic similarity, since entities are graph-members of communities and their descriptions represent the substance of those communities.

## Decision

Embed each entity's `name + description` text during extraction and store the embedding in a dedicated Qdrant collection, keyed by `(root_id, entity_id)`. On `search_global`, before triggering report generation:

1. Embed the query independently for entity search. On the first-query path — the exact latency case this design targets — no community reports exist yet, so the community-search embedding has not necessarily run; entity targeting therefore does not assume a reusable query embedding and embeds the query itself. Embedding is a single cheap inference call, so embedding independently is negligible and avoids coupling to community-search internals.
2. Semantic-search entity embeddings in Qdrant to find the top-K most relevant entities for this root.
3. Map matched entities to their community IDs (via the existing entity→community membership in the graph store).
4. Trigger `schedule_reports` only for those targeted communities, not all communities in the root.
5. Summarize and embed only the targeted communities; serve results from those reports.

## Considered Options

- **Embed entities eagerly during extraction** *(chosen)* — descriptions are already LLM-produced text; embedding them costs only embedding inference (cheap, batched), no new LLM calls. Available immediately after extraction without blocking `search_global`.
- **Embed entities lazily on first `search_global`** — defers cost but means the first query still stalls (embedding all entities for the root before any targeted selection is possible). Saves embedding cost for roots never queried at the price of latency parity with the current design.
- **Infer community topics from member entities, embed topics** — fewer embeddings (one per community, not per entity), but requires an extra LLM synthesis step before selection can happen; reintroduces LLM cost at selection time, partially defeating the goal.

## Consequences

- **First-query latency** drops from O(all communities) LLM calls to O(targeted communities) LLM calls. For a root with C communities where only T are relevant (T ≪ C), the saving is proportional.
- **Indexing cost** increases by one embedding inference call per entity (batched; no additional LLM calls). Storage footprint adds one Qdrant point per unique entity.
- **Coverage is partial by design**: `search_global` now returns reports only for the targeted communities. Callers must treat `incomplete: true` as expected behavior when fewer than all communities are summarized. For genuinely broad or architectural queries ("how is this repo organized?"), entity targeting may resolve to only a few communities and trigger the 30% cap or zero-match fallback (ADR-0011), causing a fall-through to full summarization. This is intentional: the cap exists precisely to avoid returning a misleadingly narrow slice for wide-ranging queries.
- **Cache interaction**: targeted communities that have already been summarized on prior queries are reused (their `report_build_id` matches the current build). Cold communities incur one-time summarization on first relevant query.
- **New Qdrant collection** (`mcp_vectors_entities`) is required. See ADR-0012. Entity embeddings and query embeddings **must use the same model and vector dimension**; a model change (e.g., switching `EMBEDDING_MODEL`) requires re-embedding the entire entities collection before targeted search will work correctly. See ADR-0012 for the model-change invariant.
- The entity→community mapping must be queryable at `search_global` time. This requires community membership to be stored in the graph store (each entity knows its `community_id`), which detection must populate.
