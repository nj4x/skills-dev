# Targeting Observability via Structured Logging, Not metrics.db Extension

## Context

ADR-0005 established `metrics.db` as the store for tool-engagement metrics: one row per tool call, recording `tool_name`, `session_id`, `root_path`, and `outcome` (success/zero_result/error). Targeted summarization introduces new observability signals specific to `search_global`: how many entities were found, how many communities were targeted, whether the 30% cap triggered, whether a zero-match fallback occurred.

Two approaches were considered: extend `metrics.db` with targeting-specific columns, or record targeting details via structured logging only.

## Decision

Keep `metrics.db` outcome-focused (unchanged). Record `search_global` targeting details via Python's `logging` module to a dedicated file-only handler (logger: `mcp_vectors.search_global.targeting`), writing one JSON-formatted line per call.

**Do not log the raw query text by default.** A semantic-search server's queries may contain sensitive or proprietary content; persisting them verbatim to a rotating file is unbounded PII/content retention and lets a single line grow arbitrarily large. By default the log records only a truncated, length-bounded `query_preview` (first `QUERY_LOG_MAX_CHARS` characters, default 64) plus a `query_hash` (short hash of the full query, for correlating repeated queries without storing their content) and `query_len`. Full raw-query logging is available but **opt-in** via `TARGETING_LOG_FULL_QUERY=true`, intended for local debugging only; even then the field is capped at a configurable maximum length to bound line size.

Log schema (one JSON object per line):
```json
{
  "timestamp": "2026-07-23T14:30:45.123456Z",
  "root_id": "abc123",
  "query_hash": "9f86d081",
  "query_preview": "parse user input",
  "query_len": 16,
  "entities_found": 20,
  "communities_targeted": 5,
  "total_communities": 50,
  "cap_triggered": false,
  "zero_match_fallback": false,
  "targeting_active": true,
  "elapsed_ms": 1234
}
```

When `TARGETING_LOG_FULL_QUERY=true`, an additional length-capped `query` field is included. `session_id` is omitted when not supplied by the caller. `fallback_reason` is not surfaced in the `search_global` response (ADR-0014 requires the response shape to remain unchanged).

## Considered Options

- **Extend metrics.db schema with nullable targeting columns** — queryable via existing metrics CLI; one store. Rejected: couples tool outcome tracking with an optimization-internal detail; sparse nullable columns in a shared table; targeting details are contextual to individual queries, not aggregate engagement metrics.
- **Separate targeting_metrics.db** — clean separation; queryable. Rejected: adds a new store with its own schema and CLI; no meaningful benefit over structured logging for a single tool's details.
- **Structured logging via Python logging module** *(chosen)* — follows existing file-only logging convention (CLAUDE.md); no new schema or store; queryable via grep/jq/log aggregation; rotation handled by `RotatingFileHandler`.

## Consequences

- `metrics.db` continues to record only `(tool_name, outcome)` aggregates. Existing `mcp-vectors metrics query` output is unchanged.
- Targeting logs are queryable by operators via standard log tools (`grep`, `jq`, log aggregation). Aggregate metrics (cap trigger rate, zero-match rate) require log parsing rather than a SQL query.
- If targeting metrics become critical for SLA monitoring or dashboards, log aggregation → metrics extraction is a straightforward addition without schema changes.
- The Python logger `mcp_vectors.search_global.targeting` can be disabled by setting its level to WARNING, providing a kill switch for high-volume deployments.
- Raw user query content is not retained by default: logs carry only a bounded `query_preview`, a `query_hash`, and `query_len`. This bounds per-line size and avoids persisting sensitive query text. Operators who need full queries for debugging opt in explicitly via `TARGETING_LOG_FULL_QUERY=true`, accepting the retention trade-off, with the field still length-capped.
- **`query_preview` is bounded-retention, not redaction.** The default 64-char preview will capture the full text of most short queries. This is an accepted trade-off: the goal is to bound log line size and limit retention of long queries, not to guarantee that no query content is ever stored. Operators with strict content-retention requirements should set `QUERY_LOG_MAX_CHARS=0` to suppress the preview entirely, keeping only `query_hash` and `query_len`.
- **`query_hash` is a collision key, not a privacy control.** It exists to correlate repeated identical queries in logs (e.g., "this query appeared 5 times today"), not to protect query content. An 8-hex-character hash (~32 bits) is reversible for low-entropy queries by dictionary or brute force. If reversibility is a concern, set `QUERY_LOG_MAX_CHARS=0` and rely on `query_len` alone for correlation hints.
