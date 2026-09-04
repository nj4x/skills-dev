# ADR-0053: Embedding Batch Failure Isolation

**Status:** Decided  
**Date:** 2026-09-03

## Context

When embedding a batch of chunks via `RAGPipeline._index_directory_parallel()`, the code uses:
```python
await asyncio.gather(..., return_exceptions=False)
```

This means a single embedding timeout or API error cancels all remaining batches in that gather, failing the entire index operation for the file/directory. The user sees "index failed" with no partial progress, even though some chunks were successfully embedded.

## Decision

Change `return_exceptions=False` to `return_exceptions=True` in embedding batch calls (rag.py:965). Collect per-chunk failures, report them in the `IndexResult` (success=false, reason="embedding_failed", details with failed chunks and error text).

Users see partial index: chunks that embedded successfully are upserted; failed chunks are skipped and listed. File-level IndexResult captures the failure so the caller knows to retry or investigate.

## Rationale

- **Observability:** Caller knows exactly which chunks failed, not just "batch failed."
- **Resilience:** Replace-safe upsert already tolerates partial state; a file with 95% chunks indexed is better than 0%.
- **Retry:** User can fix the root cause (e.g., LLM timeout, API rate limit) and re-run; partially-indexed content is preserved.
- **Cost:** One-line change; gather already captures exceptions, just suppresses them.

## Consequences

- Batch failures no longer cascade to directory-level failure. A directory with 1 bad file still indexes 99 good files.
- IndexResult.success changes meaning: true = file indexed (possibly partial), false = no chunks indexed (catastrophic parse error, file locked, etc.).
- Callers must decide: log partial results as warnings, or treat them as non-fatal.
