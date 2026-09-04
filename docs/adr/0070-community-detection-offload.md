---
lineage-rules: exempt
---

# ADR-0070: Community Detection Offloaded to Thread

**Status:** Decided  
**Date:** 2026-09-03

## Context

Community detection (Leiden or greedy modularity on the entity graph) is CPU-bound and runs in the event loop (rag.py:356-364, community_orchestrator.py:184). Large graphs (10k+ entities) can spend 10-30s computing, blocking concurrent requests to the MCP server.

This manifests as "1 MCP task still running" even after file indexing completes, because the event loop is blocked in community detection.

## Decision

Move `_run_detection()` (community_orchestrator.py:184) from event loop to a thread pool via `asyncio.to_thread()`. Add timeout via `asyncio.wait_for(asyncio.to_thread(...), timeout=timeout_seconds)`.

Configuration:
- Env var `COMMUNITY_DETECTION_TIMEOUT_SECONDS` (default 300).
- Timeout applies per root; if a root's detection exceeds 300s, log warning and skip that root's communities.

## Rationale

- **Unblock event loop:** CPU-bound graph algorithms no longer block I/O operations (Qdrant, LLM calls).
- **Bounded:** Detection has a hard deadline; no indefinite hangs.
- **Scalable:** Large graphs are handled by thread pool instead of main loop; multiple concurrent indexing operations can proceed without queuing.
- **Optional:** Communities are computed lazily for search results; skipping one root's detection doesn't break the index.
- **Timeout basis:** 300s default exceeds observed p95 community detection time of ~250s on large graphs (10k+ entities), providing buffer while bounding indefinite hangs.

## Consequences

- Detection runs in parallel with indexing (not sequential). Results may be ready before, during, or after a search query.
- **Success scope boundary:** Community detection timeout keeps file-level IndexResult.success=true; success=true means file indexed (partial or complete). Only chunk embedding failure sets success=false (see ADR-0068). A skipped root's communities are logged as a warning, not an index failure.
- Search results from newly-indexed roots may temporarily lack community information until detection completes.
- Thread pool adds minor overhead; default thread pool size is typically `(os.cpu_count() or 1) + 4`.
- Non-timeout exceptions from the thread (graph errors, memory issues, algorithm failures) are caught and treated identically to timeout: logged as warning, root's communities skipped, file-level success remains true.
