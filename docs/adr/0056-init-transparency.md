# ADR-0056: Initialization Transparency and Configurable Autostart

**Status:** Decided  
**Date:** 2026-09-03

## Context

On first call to `index_codebase()`, the MCP server performs initialization (rag.py:279-313) which includes:
1. Model loading on cold start (lm_studio.py:323-355) — blocks 30s to several minutes.
2. Qdrant Docker autostart if unreachable (qdrant_autostart.py:88-128) — blocks up to 90s.

Callers see no progress during this initialization; the tool appears to hang, and the user has no idea if it's waiting on LM Studio, Docker, or something else.

Env var `QDRANT_DOCKER_AUTOSTART` already exists (default true); `EXTRACTION_TIMEOUT_SECONDS` does not.

## Decision

1. **Explicit init errors with elapsed time:** When init fails (e.g., LM Studio doesn't respond in 120s, Docker unavailable), the error message includes the component that failed and how long was spent attempting it. Example: `"LM Studio model loading exceeded 120s timeout; model not loaded or service unreachable."`

2. **Respect existing `QDRANT_DOCKER_AUTOSTART` config:** Verify it's wired and documented. If false, skip autostart and fail fast if Qdrant is down.

3. **No eager init at server start:** Init remains lazy (triggered on first tool call). This keeps startup fast and doesn't penalize servers that never call `index_codebase()`.

## Rationale

- **Honesty:** User knows what init blocked on, not just "tool took 90s."
- **Predictability:** Users can configure autostart off and manage Qdrant manually.
- **Simplicity:** Lazy init is lower-risk than eager init; no new startup paths to test.
- **Observability:** Elapsed time in error messages helps users tune timeouts for their hardware.

## Consequences

- First `index_codebase()` call may return an init error instead of success. Caller must retry after fixing the underlying issue (LM Studio, Docker, etc.).
- Config `QDRANT_DOCKER_AUTOSTART` becomes discoverable in error messages and docs.
- Users can opt out of autostart and see fast failures instead of 90s waits.
