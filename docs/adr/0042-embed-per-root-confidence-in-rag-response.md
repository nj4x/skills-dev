# Embed per-root confidence in RAGResponse — close search_code seam

`server.py`'s `search_code` handler reached past `RAGPipeline`'s interface to call `pipeline._compute_confidence(root_id)` — a private method — after calling `pipeline.search()`. ADR-0024 closed the same pattern for community tools; this is its follow-up for the search seam.

`server.py`'s `search_code` handler computes confidence at line 909 after calling `pipeline.search()`. We move this computation into the pipeline by (1) hoisting the existing `_root_id` assignment (rag.py:1141, currently used by `_maybe_rerank_by_entity_graph`) above the empty-results early return, and (2) setting `RAGResponse.confidence = self._compute_confidence(_root_id) if _root_id is not None else None` on both success return paths (the empty-results and normal success paths). We add a nullable `confidence` field to `RAGResponse` to hold this value. The `search_code` handler reads `response.confidence` directly; the private-method call is removed.

## Considered options

**Surgical per-root fix (A — chosen):** add a nullable `confidence` field to `RAGResponse`; hoist the existing `_root_id` assignment above the empty-results early return, then set `RAGResponse.confidence = self._compute_confidence(_root_id) if _root_id is not None else None` on both success return paths. Zero changes to `VectorStoreProtocol`, `qdrant.py`, or `testing.py`. `search_documents` (which doesn't pass `root_path`) gets `confidence = None`. Closes the exact seam with minimal surface area.

**Multi-root aggregate (B):** compute weakest-link confidence across all Roots that contributed results by adding a new `SearchResult.root_id` field, updating `VectorStoreProtocol` and adapters, and building a `roots_involved` list in `RAGResponse.confidence`. Rejected: scope creep beyond the stated task (close the server.py private-method call). Deferred as a separately tracked follow-up, per the ADR-0024 precedent of deferring extras rather than bundling them.

**Naive uniform (C):** call `_compute_confidence(None)` for all searches. Rejected: returns a dict with `"level":"full"` (reason: `"no_graph_data"` or `"graph_disabled"`) — a false "full" signal misrepresenting the actual graph state.

## Consequences

- `RAGResponse.confidence` is an optional field (`dict | None`) — populated only when `root_path` is provided (on both success return paths). When `root_path` is `None` (e.g., `search_documents`), `confidence` is `None`. This requires an explicit guard: `confidence = self._compute_confidence(_root_id) if _root_id is not None else None`, applied identically to both the empty-results and normal success return paths, preventing the false-"full" signal that Option C (calling `_compute_confidence(None)`) would produce.
- Moving `_root_id` computation before the empty-results early return and guarding the confidence assignment on `_root_id is not None` ensures backward-compatibility: zero-hit `search_code` calls return a real confidence dict (not `null`), while `search_documents` calls return `confidence=None`.
- The error-path return `RAGResponse(False, ...)` leaves `confidence` unpopulated (default `None`). Since `server.py:905-906` returns early on `not response.success`, the error-path value is never surfaced. Moving the confidence computation inside `search()`'s try/except means its scope changes: a raise in `_compute_confidence` (today happening in `server.py` outside the except handler) would now convert a successful search into an error response. Given `_compute_confidence`'s defensive implementation and high specificity (reading only `_graph_stats` dict lookup), this risk is low but documented here.
- `_compute_confidence` remains private. Other internal callers (e.g., `search_with_response`, `search_global`) continue unchanged — they are not seam leaks and retain their current exception handling.
- `search_code` removes the private `pipeline._compute_confidence(root_id)` call (server.py:909) and instead reads `response.confidence`.
- Zero changes to `VectorStoreProtocol`, `qdrant.py`, or `testing.py`.
- Multi-root weakest-link aggregation and `search_documents` confidence are separately tracked follow-ups, enabling independent design and review.
