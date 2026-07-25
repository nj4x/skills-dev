# Replace report build-state getter/setter pairs with atomic domain operations

`GraphStore` exposes 8 getter/setter pairs — 16 methods total — for four `meta` columns
(`reports_dirty`, `reports_committed_build_id`, `reports_claimed_build_id`,
`reports_claim_lease_seconds`). Callers in `rag.py`, `server.py`, and
`community_orchestrator.py` must understand the column relationships and compose
multi-step reads and writes themselves. We decided to replace them with four atomic
domain operations that match the vocabulary of the Report Build lifecycle:

- `claim_report_build(root_id, build_id, lease_seconds) → str | None` — CAS acquire;
  returns a per-claim UUID token on success, `None` if the slot is busy or reports are
  already committed for this `build_id`. The token is the ownership discriminant for
  release (not `build_id` — see below).
- `commit_report_build(root_id, build_id, claim_token) → bool` — ownership-checked
  commit: inside a `BEGIN IMMEDIATE` transaction, verifies that
  `claimed_build_id == build_id AND claim_token == reports_claim_token`, then
  atomically writes `reports_committed_build_id = build_id`, `reports_dirty = 0`, and
  nulls the claim slot. Returns `True` if the commit was applied, `False` if this
  process no longer owns the slot (superseded by a newer generation or a faster
  same-generation peer). The caller (orchestrator) passes the token it received from
  `claim_report_build`. Clearing the slot on commit prevents it from blocking
  `claim_report_build` for the next generation during the remaining lease window.
- `clear_report_claim(root_id, claim_token) → bool` — CAS release: clears the slot
  **only** when `reports_claim_token == claim_token`; returns `True` if this caller
  owned the claim, `False` if the token does not match (slot empty, or re-claimed by
  another process with a different token).
- `report_build_status(root_id) → ReportBuildStatus` — single-call read.

Each method executes its read-modify-write inside one `BEGIN IMMEDIATE` transaction,
matching the atomicity pattern established by `claim_community_build`. Callers see
domain vocabulary instead of column names; invariants (e.g. "a claim has a lease")
are enforced inside the database layer, not scattered across callers.

**Why a per-claim token, not `build_id`, as the ownership discriminant for
`clear_report_claim`:** report `build_id` is deterministic — it equals detection's
committed `build_id` (ADR-0023). Two processes that race for the same generation use the
*same* `build_id`. If release were keyed on `build_id`, process A's failure-path
`clear_report_claim` would still match process B's live re-claim (they share the
`build_id`), defeating the ownership guard. The per-claim UUID token is minted fresh
at each `claim_report_build` call and stored in `reports_claim_token TEXT`; it is unique
per claim instance, not per generation, so A's stale token cannot match B's new token
after a re-claim.

## Consequences

- New schema columns (replacing `reports_claim_lease_seconds INTEGER`):
  - `reports_claim_expires_at REAL` — absolute epoch, matching
    `community_build_state.lease_expires_at`.
  - `reports_claim_token TEXT` — per-claim UUID, fresh on each successful
    `claim_report_build` call.
- **Schema migration:** the per-root SQLite files under `GRAPH_DB_DIR` are rebuildable
  local caches (their source of truth is the corpus plus the LLM), never a system of
  record. We therefore migrate by **schema-version bump + discard-and-recreate**, not by
  `ALTER TABLE`. On open, if the stored `schema_version` is below the version that
  introduces the new columns, the store drops and recreates the per-root DB (setting
  `reports_dirty = 1` so detection and report generation re-run on next query). This
  avoids fragile column-add/back-fill logic at the cost of one-time re-detection and
  re-generation per root — acceptable because both phases are already
  regenerated-on-demand and gated behind the Readiness Protocol. Note the true one-time
  cost: dropping the per-root DB also discards the entity graph, forcing entity
  re-extraction (which may incur LLM calls, not just clustering) on next index, in
  addition to community re-detection and report re-generation. This is heavier than
  "re-detection" alone implies, but is still a bounded one-time hit per root and the
  vector store (the expensive embeddings) is untouched.
- **Migration is serialized by the write lock.** The `schema_version` check and
  discard-and-recreate both run inside a `BEGIN IMMEDIATE` + `_write_lock` transaction on
  the per-root file. Only the first process to acquire the write lock performs the drop
  and recreate; any concurrent opener blocks and, on entry, reads the already-migrated
  `schema_version` and skips the recreate.
- The 16 getter/setter methods are removed. The three test files covering them
  (`test_graph_store_reports.py`, `test_community_orchestrator.py`) must be updated to
  call the new domain operations.
- `community_orchestrator._run_reports_attempt` stores the token returned by
  `claim_report_build` and returns immediately when `claim_report_build` returns `None`.
  On the success path the orchestrator calls `commit_report_build(root_id, build_id,
  token)`, which marks completion and clears the claim atomically. On the
  failure/cancellation path it calls `clear_report_claim(root_id, token)`.

**`ReportBuildStatus` fields** (returned by `report_build_status`):
```python
@dataclass
class ReportBuildStatus:
    committed_build_id: str | None   # last fully committed report build
    dirty: bool                      # True if reports are stale vs. current detection
    claimed_build_id: str | None     # build currently being generated (or None)
    claim_expires_at: float | None   # absolute epoch; None if unclaimed
```
