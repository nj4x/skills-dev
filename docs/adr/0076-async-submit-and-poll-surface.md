---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0076: Async Submit and Poll Surface for ask_peer_model

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

Map issue #52 extends cline-bridge with async delegation. The existing `ask_peer_model(question, repo_path)` blocks the caller for up to 180 seconds, suitable for quick oracle questions (10–15s typical). Ticket #57 adds a non-blocking variant for delegated work (minutes scale), where the capable agent submits a question and checks back later for the answer.

ADR-0069 through ADR-0075 have settled queue schema, thread scoping, worker identity, and repo access. This ticket completes the MCP surface.

**Decision**

## Two async variants, blocking `ask_peer_model` unchanged

Keep the existing `ask_peer_model(question: str, repo_path: str) -> {id, status, answer, reason}` unchanged — it is proved valuable for the oracle use case and has callers already depending on it.

Add two new tools:

```python
submit_to_peer_model(question: str, repo_path: str, thread_id: str | None = None) -> {handle: str | None, status: "submitted" | "failed", reason: str | None}
```

Returns immediately with a request handle. The capable agent can submit many questions before polling any of them. `status: "failed"` covers submission-time errors only — `reason: "queue_unavailable"` (filesystem/lock error, matching `ask_peer_model`'s existing reason of the same name) or `reason: "repo_path_mismatch"` (thread's first message set a different `repo_path`, per ADR-0075). `handle` is `None` whenever `status` is `"failed"`.

```python
poll_peer_model(handle: str, thread_id: str | None = None) -> {status: "pending" | "answered" | "failed", answer: str | None = None, reason: str | None = None}
```

Polls the status of a previously-submitted request. Returns immediately; no blocking.

## Handle format and thread-aware resolution

The handle is literally the request `id` field from the submitted record (a timestamp-uuid composite, per ADR-0069 `submit()`). The capable agent supplies the same `thread_id` on poll as it did on submit, so `poll_peer_model` can resolve through the `locate(id, thread_id)` rule already defined in ADR-0073.

No new token format or encoding — the handle is human-inspectable (useful for debugging) and carries enough information to retrieve the record from the filesystem. Encoding `thread_id` into the handle itself was considered (it would remove the caller's obligation to pass `thread_id` on poll, closing the misrouted-handle failure mode described below) and rejected: it means inventing and versioning a composite token format for a problem the caller already has to solve, since it must track `thread_id` per handle anyway to submit follow-ups correctly.

When polling, if `thread_id` is `None` (unthreaded request), the record is read from top-level `queue/answered/` or `queue/failed/`. If `thread_id` is set, it is read from `queue/threads/<thread_id>/answered/` or `queue/threads/<thread_id>/failed/`.

The blocking `ask_peer_model`'s `id` is a legal `poll_peer_model` handle (with `thread_id=None`, since `ask_peer_model` never sets one): both surfaces share the same record store and `locate()` rule. This is useful if a worker answers just after `ask_peer_model`'s own 180s deadline fires — the record is already in `failed/` from the caller's perspective, but if it was answered a moment later a poll would still find it in `answered/` rather than `failed/`, letting a caller that kept the `id` recover a late answer instead of discarding it.

## No precheck: accept every submission unconditionally

`submit_to_peer_model` does not check whether any worker is currently alive. The submitting agent is not blocked, so a pool opened later can still pick up the work. Fast-fail on worker status is not necessary.

A record that sits in `pending/` for the full async timeout is swept to `failed/` with `reason: "timeout"` — the gc() sweep inspects only the filesystem timestamp and cannot determine whether any worker was ever alive, so no distinct `worker_offline` reason is emitted for the async path. (`worker_offline` remains available only in the blocking `ask_peer_model`, where liveness is checked synchronously before submission.)

## Async timeout: 30 minutes, enforced by gc() sweep

The blocking `ask_peer_model` times out after 180 seconds because its caller is stuck waiting. Async work operates on a different timescale — the map's Notes specify minutes. A new environment variable `CLINE_BRIDGE_ASYNC_TIMEOUT` (default 1800 seconds = 30 minutes) governs when an unanswered async request is terminal.

The timeout is enforced by extending ADR-0073's `gc()` sweep. Currently it removes records from `answered/` and `failed/` older than `RETENTION_SECONDS` (7 days). The extended sweep also marks a record as failed (`reason: "timeout"`) if it was submitted more than `CLINE_BRIDGE_ASYNC_TIMEOUT` seconds ago and sits in:

- top-level `queue/pending/` or `queue/claimed/`, **or**
- any `queue/threads/<id>/pending/`.

**Only thread `claimed/` records are exempt** from this sweep — those are covered by ADR-0073's staleness sweep instead. That sweep's 180s claimed-staleness threshold (ADR-0068 point 5) was set for the blocking oracle path, where 180s is the caller's own timeout and a claim outliving it means the holder is dead. Threading exists only on the async surface — the blocking `ask_peer_model` never sets `thread_id` — so every thread-scoped claim is, by construction, async work that may legitimately run for minutes. **This ADR raises ADR-0073's claimed-staleness threshold from a flat 180s to `CLINE_BRIDGE_ASYNC_TIMEOUT` for thread-scoped claims specifically**, superseding that one number in ADR-0073 without otherwise changing its sweep logic. The unthreaded 180s threshold is untouched — it still governs `ask_peer_model`'s own top-level claims.

Thread `pending/` records get no exemption: a threaded record — first message or follow-up — that sits unclaimed for `CLINE_BRIDGE_ASYNC_TIMEOUT` is abandoned and must time out, otherwise a thread whose first message nobody ever claims accumulates forever (neither this sweep nor ADR-0073's excludes it, since no `continuation_deadline` is ever set on an unclaimed record).

This is safe for an *active* thread's follow-up: `CLINE_BRIDGE_ASYNC_TIMEOUT` (30 min default) is an order of magnitude longer than the 5-minute idle timeout ADR-0073 uses to keep a thread alive between messages, so a follow-up submitted into a live thread is claimed, answered, or continuation-deadline-swept long before this sweep would ever touch it.

The sweep runs on every call to `ask_peer_model`, `submit_to_peer_model`, and `poll_peer_model` (all three advance the frontier), so a fully quiescent bridge with no active agent runs no sweep.

`poll_peer_model` will return `status: "failed"` with `reason: "timeout"` for a handle that has been swept as stale.

## Reasons returned by poll_peer_model

- `status: "pending"`: Record exists and is still unclaimed or claimed but not answered. Caller should check back later.
- `status: "answered"`: Record is answered. The `answer` field contains the text.
- `status: "failed"`, `reason: "timeout"`: Record was submitted but not answered within `CLINE_BRIDGE_ASYNC_TIMEOUT` (covers both "no worker ever claimed it" and "a worker claimed it but never answered" — gc() cannot and does not distinguish these).
- `status: "failed"`, `reason: "unknown_handle"`: The handle does not exist in any queue directory reachable via `locate(id, thread_id)`. This covers "never submitted", "older than 7-day retention", and "submitted with a different `thread_id` than the one passed to poll" (see Thread invariant below) — the filesystem cannot distinguish any of these.
- `status: "failed"`, `reason: "internal_error"`: Any other server-side failure (e.g., queue I/O error). Not enumerated further; callers must treat any reason value they don't recognize as terminal, not as pending.

This is a closed set only for the cases this ADR defines; it is not exhaustive against future additions.

## Thread invariant: serial submission, unenforced

ADR-0073 requires the capable agent to not submit a follow-up until the prior message is answered (the routing check depends on directory state set by the claim). `submit_to_peer_model` does not enforce this — it is a caller contract, consistent with ADR-0073's decision to keep the queue stateless with respect to ordering.

A caller that violates this (submits two messages before the first is claimed) has the second land in top-level `queue/pending/` instead of `queue/threads/<id>/pending/`. The observable failure is on the poll side, not the answer side: `poll_peer_model(handle, thread_id=X)` resolves through `locate(id, thread_id)`, which for a non-null `thread_id` searches only `queue/threads/<id>/...`. It will not find a record that landed in top-level `queue/`, so it returns `reason: "unknown_handle"` — indistinguishable from a handle that never existed. The misrouted record itself may still be claimed and answered by some worker outside the thread's context, but the caller that expected it under `thread_id` has no way to retrieve that answer through `poll_peer_model`. The burden is on the capable agent to submit serially.

## Consequences

- **`server.py` gains two new tool handlers.** Both call `gc()` first, then `submit()` or `read_answered()` respectively. Errors are returned as `{status: "failed", reason: ...}` tuples.

- **`BridgeQueue.submit()` must now store `thread_id` and `repo_path` on every record** — they are already in the schema per ADR-0073 and ADR-0075, but `submit()` currently does not accept or store them. Update the signature and record schema.

- **`BridgeQueue.read_answered()` must take `thread_id` and use `locate()`.** Currently it reads only from top-level `queue/answered/`; it must now resolve through the `locate(id, thread_id)` rule from ADR-0073. `poll_peer_model`'s handler checks, in order: `answered/` (found → `status: "answered"`), `failed/` (found → `status: "failed"`, `reason` read from the record's `reason` field), `pending/` or `claimed/` (found → `status: "pending"`, no distinction exposed to the caller between the two), not found in any of the four → `status: "failed"`, `reason: "unknown_handle"`.

- **`gc()` gains the async timeout sweep.** Check `submitted_at` on every record in `queue/pending/`, `queue/claimed/`, and `queue/threads/*/pending/`; if older than `CLINE_BRIDGE_ASYNC_TIMEOUT`, move it to the `failed/` directory that `locate()` resolves for that record (top-level or thread-local) with `reason: "timeout"`. Thread `claimed/` is skipped — ADR-0073's staleness sweep owns it.

- **The sweep is safe under concurrent callers.** Every record transition is a single `os.rename`, which is atomic within a filesystem; two `gc()` runs racing on the same record produce one successful rename and one `OSError` on the vanished source, which the existing `gc()` already swallows (`bridge/queue.py:151`). No additional locking is introduced for the sweep.

- **The record schema gains a `reason` field.** ADR-0073's `fail()` only renames a record into `failed/`, recording nothing about why. `poll_peer_model` reports `reason`, so the value must be persisted on the record at the moment it fails — `timeout` from the sweep, or whatever the caller-side `fail()` path supplies. A record read from `failed/` with no `reason` set is reported as `internal_error`.

- **Worker prompt and docstrings must clarify async work is valid.** The existing prompt is silent on async; add a line: "You may be answering an async request, where the caller is not blocked on you — take the time to give a thorough answer, but note the request still expires after `CLINE_BRIDGE_ASYNC_TIMEOUT` (30 minutes by default), after which your answer is discarded."

- **Handles themselves are opaque to the caller but human-readable on inspection.** If a caller loses track of handles, they can manually scan `queue/` directories to find records. No database — the filesystem is the store.

- **The capable agent must manage its own handle list per thread.** If it opens a thread and submits three questions, it tracks those three handles itself; there is no "list handles in this thread" query. This is acceptable because a thread is typically short-lived (one or two follow-ups) and the capable agent already maintains the thread UUID.

- **Cancellation is out of scope.** There is no `cancel_peer_model(handle)`. A submitted request that the caller no longer wants sits until `CLINE_BRIDGE_ASYNC_TIMEOUT` retires it or a worker answers it into the void; the caller simply stops polling. If cancellation proves necessary in practice, it is a follow-up ticket, not part of this design.
