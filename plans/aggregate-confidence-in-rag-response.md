Design decisions reached during grilling on candidate #1 from the mcp-vectors architecture review (2026-07-24): embed per-root confidence in RAGResponse, closing the server.py private-method seam leak identified as an ADR-0024 follow-up.

- docs/adr/0042-embed-per-root-confidence-in-rag-response.md

---

## Session Ledger

| Role         | Outcome           |
|--------------|-------------------|
| orchestrator | —                 |
| planner      | complete (grilling) |
| critic #1    | revise (major)    |
| critic #2    | revise (major)    |
| critic #3    | revise (major)    |
| critic #4    | approve (minor)   |

## Critic Review

- **Final verdict:** approve
- **Severity:** minor
- **Iterations used:** 4
- **Approval status:** ✓ Automatically approved by critic. No manual review required.

### Remaining minor notes (non-blocking)

- Hoist `_root_id` above the empty-results early return to avoid duplicate computation.
- Line number references may drift; use anchors (return statements) instead.
- `_compute_confidence` is now inside `search()`'s try/except; if it raises, a successful search converts to an error response. Risk is low given its defensive implementation, but document the exception-scope change.
- Empty root_path behavior: `root_path` in `('', None)` both yield `confidence=None`; confirm this matches intended semantics for `search_code` (which never passes empty roots after `resolve_path`).
