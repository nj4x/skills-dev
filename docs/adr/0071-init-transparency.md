---
lineage-rules: exempt
---

# ADR-0071: Initialization Transparency and Configurable Autostart

**Status:** Decided  
**Date:** 2026-09-03  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

On first call to `index_codebase()`, the MCP server performs initialization (rag.py:279-313) which includes:
1. Model loading on cold start (lm_studio.py:323-355) — blocks 30s to several minutes.
2. Qdrant Docker autostart if unreachable (qdrant_autostart.py:88-128) — blocks up to 90s.

Callers see no progress during this initialization; the tool appears to hang, and the user has no idea if it's waiting on LM Studio, Docker, or something else.

Env var `QDRANT_DOCKER_AUTOSTART` already exists (default true); `EXTRACTION_TIMEOUT_SECONDS` does not.

## Decision

1. **Explicit init errors with elapsed time:** When init fails (e.g., LM Studio doesn't respond in 120s, Docker unavailable), the error message includes the component that failed and how long was spent attempting it. Example: `"LM Studio model loading exceeded 120s timeout; model not loaded or service unreachable."`

2. **Respect existing `QDRANT_DOCKER_AUTOSTART` config:** `QDRANT_DOCKER_AUTOSTART` env var is wired (default true, set in qdrant_autostart.py:96). When false, autostart is skipped and Qdrant-down errors fail fast.

3. **Init timeout:** Default 120s, env-overridable via `INIT_TIMEOUT_SECONDS`. The init sequence is wrapped in this timeout. Upon timeout, fail immediately with the same message format as other init failures (elapsed time + component).

4. **No eager init at server start:** Init remains lazy (triggered on first tool call). This keeps startup fast and doesn't penalize servers that never call `index_codebase()`.

5. **Init failure is atomic:** Init failure aborts `index_codebase()` immediately. The caller receives the init error before any files are indexed; there is no degraded partial-indexing mode. Either init fully succeeds and indexing proceeds, or init fails and zero files are indexed.

## Rationale

- **Honesty:** User knows what init blocked on, not just "tool took 90s."
- **Predictability:** Users can configure autostart off and manage Qdrant manually.
- **Simplicity:** Lazy init is lower-risk than eager init; no new startup paths to test. Atomic init failure avoids ambiguous partial states that would complicate retry logic.
- **Observability:** Elapsed time in error messages helps users tune timeouts for their hardware.

## Consequences

- First `index_codebase()` call may return an init error instead of success. Caller must retry after fixing the underlying issue (LM Studio, Docker, etc.).
- **Atomicity:** Init failure aborts `index_codebase()` entirely — no files are indexed when init fails, and the caller never sees an init error coexisting with partial index results.
- Config `QDRANT_DOCKER_AUTOSTART` becomes discoverable in error messages and docs.
- Users can opt out of autostart and see fast failures instead of 90s waits.
- Init now has a hard timeout (default 120s via `INIT_TIMEOUT_SECONDS`); model loading or Qdrant connection hangs are bounded rather than indefinite.
