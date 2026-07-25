# Entity Search Scope: K=20, 30% Community Cap, Zero-Match Fallback

## Context

ADR-0009 and ADR-0010 establish that `search_global` uses semantic entity search (Qdrant) to identify which communities to summarize, rather than summarizing all communities upfront. The selectivity of this approach depends on how many entities are retrieved and how they map to communities. Two failure modes exist:

- **Over-retrieval**: retrieving many entities that span most communities collapses the optimization back toward full summarization, with added overhead.
- **Zero-match**: the query returns no entity hits (query is outside the entity vocabulary), leaving no communities to target — the system must not return empty results.

## Decision

**Top-K entity retrieval:** Retrieve the top `K=20` most semantically similar entities per `search_global` call. Configurable via `ENTITY_SEARCH_LIMIT` environment variable.

**30% community cap:** After resolving matched entity IDs to community IDs via the SQLite join table (ADR-0010), count the distinct targeted communities. If targeted communities exceed `ceil(total_communities_for_root * 0.3)`, discard the targeted set and fall back to full community summarization. This threshold signals that the entity graph is too inter-connected for selective targeting to save meaningful work.

**Zero-match fallback:** If Qdrant entity search returns no results, fall back immediately to full community summarization — the same path used before this feature existed. This handles queries that lie outside the entity vocabulary (e.g., very abstract or domain-novel phrasing).

## Considered Options

- **Fixed K, no cap** *(simpler)* — retrieve K entities, target whatever communities result, no safety valve. Risk: a highly-connected graph maps 20 entities to 40 out of 50 communities; the latency win disappears silently.
- **K=20 + 30% cap + zero-match fallback** *(chosen)* — explicit degradation point; the system self-corrects to full summarization when targeting would be futile, and the K is tunable without code changes.
- **Adaptive K based on community count** — scale K proportionally to the root's community count. Added complexity with unclear benefit; the 30% cap already provides the safety valve without per-root tuning.

## Consequences

- `search_global` gains a new early decision branch: retrieve entities → map to communities → check cap → branch to targeted or full summarization path.
- The 30% threshold is a tuning knob. At 30%, a root with 10 communities caps at 3 targeted; a root with 100 communities caps at 30. If the cap fires frequently in practice (observable via metrics), it should be lowered; if targeted search is rarely selective enough, the entity embedding approach itself should be reconsidered.
- Zero-match fallback is fully transparent to callers — `search_global` response shape is unchanged; the `incomplete` flag signals partial coverage as before.
- `ENTITY_SEARCH_LIMIT=20` is the shipped default. Operators with large, densely connected graphs may need to lower it; sparse/modular graphs may benefit from raising it.
