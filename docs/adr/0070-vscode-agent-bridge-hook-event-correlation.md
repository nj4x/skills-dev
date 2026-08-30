---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0070: Correlate hook events by cline taskId in vscode-agent-bridge

**Date:** 2026-08-29

**Status:** Accepted

## Context

The bridge's hook server attributes every `/hook` POST positionally: "whichever record the queue holds in flight is the one it's about" (`bridge/hookserver.py` module docstring). No identifier from the payload is read.

This assumption breaks on task handoff inside cline-sr. When the bridge dispatches a new task via the `/task` URI handler while cline-sr still has its previous task open, cline-sr aborts the old task first — firing a `TaskCancel` hook ~150ms after dispatch. That payload describes the **old** task (`taskCancel.taskMetadata.taskId`, `completionStatus: "abandoned"`), but the bridge attributes it to the freshly dispatched record: the record flips `dispatched -> failed (reason=cancelled)` and `_in_flight` is cleared. The real task's `TaskStart`/`PreToolUse`/`PostToolUse`/`TaskComplete` then find no in-flight record (logged `task=-`), and `BridgeQueue.complete()` silently drops the finished answer. The caller is told the task was cancelled while cline-sr in fact completed it — observed 8 times in one session (task `c06869fe…`, 2026-08-29, session log).

cline-sr's hook payload shapes (verified against the extension bundle, 2026-08-29):

- `TaskStart`, `TaskComplete`, `TaskCancel` carry `taskMetadata.taskId` (plus a ulid; `TaskCancel` also carries `completionStatus`). Real correlation is possible for these events.
- `PreToolUse` = `{preToolUse: {toolName, parameters}}` and `PostToolUse` = `{postToolUse: {toolName, parameters, result, success, executionTimeMs}}` — **no taskId or taskMetadata at all**. Tool-use events cannot be correlated by id.

Bridge-side facts relevant to the mechanism: `Record` (`bridge/queue.py:27-38`) has no cline-task-id field today; `_records` is keyed by bridge uuid (`queue.py:49`); `cancel()` clears `_in_flight` (`queue.py:94-95`); tool-use events are handled positionally at `hookserver.py:87-88`.

## Decision

Replace positional attribution with **bind-and-filter by cline taskId**:

1. **Bind on TaskStart.** When `TaskStart` arrives and the in-flight record has no bound cline taskId, bind `taskMetadata.taskId` to it. `Record` gains a field to hold it: `cline_task_id: str | None = None`.
2. **Filter TaskCancel and TaskComplete only.** `TaskCancel` and `TaskComplete` apply to the in-flight record only when the payload taskId matches the bound one. Mismatches are logged and dropped. `PreToolUse`/`PostToolUse` remain positionally attributed — their payloads carry no taskId (see Context), so no filter is possible. This is safe: tool-use events only bump heartbeat counters (`record_tool_use()`), and the only misattributable event observed in practice is the old task's cancel, which arrives before bind and is handled by rule 3.
3. **Cancel before bind is teardown.** A `TaskCancel` arriving while the in-flight record is dispatched-but-unbound is the previous task's teardown — logged and ignored, never applied to the new record.
4. **Late-completion recovery.** A `TaskComplete` whose taskId matches a record already marked `failed` resurrects it (`failed -> answered`), so `poll_peer_agent` can still retrieve the result. This matches the existing contract that a timed-out handle may be re-polled to recover a late answer. `ask()` calls that already returned `failed` are not unwound.

   *Lookup mechanism:* since `_records` is keyed by bridge uuid and `_in_flight` is cleared on cancel, recovery resolves the record by a **linear scan over `_records.values()` matching `cline_task_id`**. A reverse index (cline-taskId → Record) is not worth its bookkeeping: the queue is small, in-memory, and short-lived, so an O(n) scan on the rare recovery path costs nothing and adds no invalidation state.

   *Why keep this point at all:* it is the recovery path for orphaned answers — if any residual misattribution, or a future cline-sr payload-shape drift, marks a record failed while cline-sr actually completes the work, the finished answer is otherwise dropped on the floor. Dropping the point would reintroduce exactly the silent-loss failure this ADR exists to fix.
5. **No silent drops.** `complete()`/`cancel()` hitting an empty or mismatched in-flight slot log a WARNING including the payload taskId, instead of returning silently.

## Considered Options

- **Ignore cancel-before-start only** (no payload parsing): minimal, but attribution stays positional, so other stale events remain misattributable. Rejected as incomplete — and under bind-and-filter you must define the unbound-cancel rule anyway (point 3), which subsumes it.
- **Discriminate on `completionStatus` (`abandoned` vs `cancelled`)**: weaker signal than taskId equality; cline's internal status semantics may not map cleanly to bridge intent. taskId matching is used instead; `completionStatus` may be logged for diagnostics.

## Consequences

- Genuine user cancels keep working **once `TaskStart` has bound**: they carry the bound taskId and pass the filter. A genuine cancel arriving in the pre-bind window (~150ms after dispatch) is indistinguishable from teardown and is treated as teardown — declared an accepted, out-of-scope case. Rationale: human reaction time makes a real cancel inside that window implausible; if it ever happens, either the task starts anyway and can be cancelled again post-bind, or the existing sweep timeout eventually fails the record. No silent hang results.
- A record's status can now leave `failed` (point 4) — callers polling a failed handle may later see `answered`.
- If `TaskStart` never arrives (dispatch lost), the record stays unbound and the existing sweep timeout fails it — unchanged behavior.
- Hook payload parsing becomes load-bearing; a cline-sr payload-shape change would degrade to log-and-drop, surfaced by the new WARNINGs.

**Lineage:** No SRS/FS anchor. Follows ADR-0069 precedent: this repo has no requirements corpus for internal tooling, and vscode-agent-bridge ADRs (0068, 0069) are exempt.
