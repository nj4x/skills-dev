# Split the Qdrant stores into async and in-memory adapters behind protocols

## Status

proposed

## Context

`QdrantVectorStore` (chunk vectors) and `QdrantCommunities` (community-report vectors) both carry an `if self._client: await … else: sync_client …` branch in nearly every method. The async path is production; the sync path exists only for in-memory tests. This duality roughly doubles each method's body and inflates the interface with modes callers should not have to track (`_client` vs `_sync_client`, branching in `_ensure_collection`, `scroll_points_bounded`, `delete_all_except`). The module's depth is halved: callers must know which mode the store was constructed in.

## Decision

Define two focused protocols — `VectorStoreProtocol` (chunk operations: `search`, `upsert_chunks`, `update_chunk_entities`, etc.) and `CommunityVectorStoreProtocol` (report operations: `search`, `upsert_generation`, `list_by_root`, `delete_all_except`, etc.). Provide `AsyncQdrantVectorStore` / `AsyncQdrantCommunities` (production, async-native, no branching) and `InMemoryVectorStore` / `InMemoryCommunities` (tests, dict-backed behind a thin async façade).

Tests inject the in-memory adapter through the pipeline's existing optional-collaborator constructor pattern (e.g. `RAGPipeline(..., vector_store=InMemoryVectorStore())`), consistent with how `lm_client` and `vector_store` are already handled today.

## Considered Options

- **One combined protocol for both stores.** Rejected: the two stores have different concerns, query patterns, and initialization; a single protocol would be fatter and obscure that distinction.
- **Split only `QdrantVectorStore`, defer `QdrantCommunities`.** Rejected: the community store carries the same duality and leaving it half-migrated keeps a mixed pattern in the codebase; do both for a complete picture.
- **Factory function or test-level fixture for adapter selection.** Rejected: constructor injection is the established pattern in this codebase; a factory adds indirection and a fixture splits bootstrap logic between test and prod.

## Consequences

- Each adapter is pure — no `if self._client` branching — so the interface contracts the same behaviour regardless of adapter.
- Production Qdrant concerns live in one class; test-only concerns in another.
- Existing test fixtures that construct `QdrantVectorStore(client=None)` / `QdrantCommunities(...)` directly must migrate to the in-memory adapters — moderate, mechanical churn.
- Tests no longer need to know whether a store was built in sync or async mode.
