---
lineage-rules: exempt
---

# ADR-0069: Entity Extraction Timeout and Failure Isolation

**Status:** Decided  
**Date:** 2026-09-03

## Context

Entity extraction runs as fire-and-forget background tasks (rag.py:716-722). If an LLM call hangs or the extraction logic stalls, the task never completes and logs only a warning (rag.py:904-910). The index operation reports success even though extraction is pending indefinitely.

Example: `index_codebase()` returns success with 100 files indexed, but file #5's extraction is stuck waiting for LLM response. User has no indication extraction is incomplete or failed.

## Decision

Add `asyncio.wait_for(extraction_coro, timeout=timeout_seconds)` around each `_extract_and_merge()` call. On timeout:
- Log a warning with file path and elapsed time.
- Count the timed-out extraction in a result field (e.g., `extraction_timeouts`).
- Do not retry; extraction is optional for search (chunks are already indexed).

Configuration:
- Env var `EXTRACTION_TIMEOUT_SECONDS` (default 120).
- Passed to RAGPipeline at init; can be overridden per-call in future if needed.

## Rationale

- **Honesty:** User knows if extraction completed or timed out (visible in result summary or logs).
- **Bounded cost:** Extraction no longer consumes unbounded time; event loop is unblocked 120s after the last chunk embedding completes.
- **Graceful:** Timed-out extraction doesn't fail the index; search still works (entities and communities are optional enhancements).
- **Observability:** Logs show which files had extraction timeouts, enabling investigation of slow LLM or large files.
- **Timeout basis:** 120s default exceeds observed p95 extraction latency of ~90s in testing, providing buffer for variation while bounding indefinite hangs.

## Consequences

- Extraction task must complete or timeout within 120s. Very large files or slow LLM may hit this; user can increase `EXTRACTION_TIMEOUT_SECONDS` if needed.
- **Success scope boundary:** Extraction timeout keeps file-level IndexResult.success=true; success=true means file indexed (partial or complete). Only chunk embedding failure sets success=false (see ADR-0068). Extraction timeouts are reported separately via the `extraction_timeouts` counter.
- Fire-and-forget tasks are now properly bounded; no indefinite hanging.
- Background task completion is no longer blocking on lifespan shutdown; even if extraction is pending, the server can shut down cleanly (after graceful timeout).
- Non-timeout extraction exceptions (parse errors, API failures, file locks) are logged as warnings and counted separately from timeouts; they do not degrade file-level success. Extraction remains optional for search.
