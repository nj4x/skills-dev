# Stalling Fix Implementation Plan

Design Decisions Reached During Grilling. ADRs below capture architecture; implementation phases follow.

## ADRs (ground truth)

- [[docs/adr/0068-embedding-batch-isolation.md]] — Embedding batch failures isolated; partial index on failure
- [[docs/adr/0069-entity-extraction-timeout.md]] — Per-file extraction timeout (120s default, env override)
- [[docs/adr/0070-community-detection-offload.md]] — Community detection to thread pool with timeout (300s default)
- [[docs/adr/0071-init-transparency.md]] — Init errors show elapsed time + component; respect autostart config
- [[docs/adr/0072-sync-strategy-for-stale-index.md]] — Staleness detection adds messaging, no auto-refresh

## Implementation scope

1. **Config layer (config.py):**
   - Add `extraction_timeout_seconds` (default 120)
   - Add `community_detection_timeout_seconds` (default 300)
   - Add `stale_index_threshold_days` (default 7)
   - Parse from env vars: `EXTRACTION_TIMEOUT_SECONDS`, `COMMUNITY_DETECTION_TIMEOUT_SECONDS`, `STALE_INDEX_THRESHOLD_DAYS`
   - Verify `QDRANT_DOCKER_AUTOSTART` exists (should already)

2. **Embedding batch isolation (rag.py, ~965):**
   - Change `await asyncio.gather(..., return_exceptions=False)` to `return_exceptions=True`
   - Collect per-chunk failures from exceptions
   - Report in IndexResult: success=true (partial), failed_chunks list, failure reason

3. **Entity extraction timeout (rag.py, ~716-722; entity_extractor.py):**
   - Wrap `_extract_and_merge()` in `asyncio.wait_for(extraction_coro, timeout=config.extraction_timeout_seconds)`
   - On timeout: log warning (file path, elapsed), increment counter
   - Return from extraction task without retry

4. **Community detection offload (community_orchestrator.py, ~184):**
   - Wrap `_run_detection()` in `asyncio.to_thread()`
   - Wrap thread call in `asyncio.wait_for(..., timeout=config.community_detection_timeout_seconds)`
   - On timeout: log warning, skip detection for that root

5. **Init transparency (rag.py, ~279-313; lm_studio.py error handling):**
   - Add elapsed-time tracking around `_detect_embedding_dimension()` and `ensure_qdrant_running()`
   - On init error, include elapsed time and which component failed
   - Example: `"LM Studio model loading took 127s and exceeded timeout; model not loaded or service unreachable."`

6. **Stale index detection (server.py, index_codebase; rag.py, get_indexing_status):**
   - Add `indexed_at` comparison logic: if (now - oldest_indexed_at) > threshold, mark stale
   - Add field to status dict: `stale_since` (ISO 8601) if stale
   - Add suggestion in result message when force=false and stale
   - Example: `"Index is stale (last updated 4 weeks ago). Use force=true to re-index or call sync_directory() to reconcile (faster)."`

## Testing considerations

- Embedding batch failure: mock LM Studio to return partial errors in gather; verify IndexResult captures failed chunks
- Extraction timeout: mock LLM to hang indefinitely; verify timeout fires, warning logged, index completes
- Community detection timeout: generate large graph; mock detection to stall; verify timeout fires, detection offloaded to thread doesn't block main loop
- Init errors: mock LM Studio unavailable; verify error includes elapsed time and component name
- Stale index: mock Qdrant metadata with old `indexed_at`; verify `stale_since` field in status

## Files to modify

- `vectors/config.py` — Add timeouts, threshold
- `vectors/rag.py` — Embedding gather, extraction wrap, init elapsed time, staleness detection
- `vectors/community_orchestrator.py` — Offload to thread
- `server.py` — Pass config to pipeline, return stale_since in status
- (optional) `vectors/lm_studio.py` — Improve init error messages with component names
