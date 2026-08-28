---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0073: Thread-Scoped Queue Directories and Per-Request Answer Files

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

Map issue #52 extends the Cline bridge (ADR-0069, ADR-0070, ADR-0071) with threaded conversations and a worker pool. Ticket #54 locked thread binding as Option C — a worker that claims the first message of a thread stays bound to it by polling `claim-next --wait N --thread <id>` in a loop, relying on Cline's own session context to carry the conversation. No external context store is needed for the *holding* worker.

That leaves a gap #54 didn't cover: with a pool of workers, other workers keep calling plain `claim-next` (no `--thread`) concurrently. If thread binding were enforced only by the holding worker choosing to filter, nothing stops an unfiltered worker's FIFO scan from claiming a follow-up meant for a held thread — the wrong session would answer with no memory of the exchange, reproducing the confabulation failure this map exists to fix.

Ticket #55 also carries forward a known v1 bug (#52 Notes): the worker is always told to stage its answer at the single static path `/tmp/bridge-answer.txt` (`bridge/cli.py:29`). With more than one worker, two workers answering concurrently can overwrite each other's staged file before either runs `bridge answer`.

**Decision**

## Thread ownership is directory location, not a guard check

ADR-0069 already treats status as "encoded by containing directory, not fields," to avoid torn-state windows. Thread ownership extends the same rule instead of adding a check: a thread's records simply become invisible to unfiltered scans once claimed, because they are no longer in the top-level directories those scans read.

```
~/.cline-bridge/queue/
├── pending/                          # unthreaded + not-yet-claimed first thread messages
├── claimed/
├── answered/
├── failed/
└── threads/
    └── <thread_id>/
        ├── .swept                    # tombstone, written by the sweep; absent while thread is live
        ├── pending/                  # follow-ups once the thread is claimed
        ├── claimed/
        ├── answered/
        └── failed/
```

**Routing rule** — `submit(question, thread_id=None)` writes to `queue/threads/<thread_id>/pending/` only when `thread_id` is set, `threads/<thread_id>/` exists, **and** `threads/<thread_id>/.swept` does not exist. Otherwise the record lands in top-level `queue/pending/`, exactly as v1 — covering unthreaded requests and the first message of a brand-new thread.

The `.swept` tombstone is what stops a dead thread from silently swallowing follow-ups. Without it, the sweep's decision to preserve a thread directory for post-mortem inspection would keep satisfying the routing check forever, and every later follow-up would accumulate in a `pending/` no worker polls.

**Claim rule:**
- `claim_next()` (unfiltered) scans only top-level `queue/pending/`. It can claim the first message of a thread but nothing routed into a `threads/` subtree.
- On claiming a record whose `thread_id` is set, `queue/threads/<thread_id>/` is created if absent (birth of the thread) and the record is moved into `queue/threads/<thread_id>/claimed/`, not top-level `claimed/`. This is the moment the thread becomes exclusively visible to its holder.
- `claim_next(thread_id=...)` (the `--thread` filter) scans only `queue/threads/<thread_id>/pending/`.

No skip-list, no lock check, no race window: an unfiltered worker cannot see what it was never scanning.

**Client invariant.** The capable agent must not submit a follow-up to a thread until the previous message in that thread has been answered. The routing check reads directory state that the *claim* creates, so a second message submitted before the first is claimed finds no thread directory and lands in top-level `pending/`, where any worker may take it. Serial submit-then-await is therefore a contract on the caller, not something the queue enforces; #57's async surface must uphold it.

## Record schema additions

```json
{
  "id": "1756205412345-a3f9c2d1",
  "thread_id": "abc123-uuid-or-null",
  "question": "What does this code do?",
  "submitted_at": "2026-08-27T14:30:12.345Z",
  "claimed_at": null,
  "claimed_by": null,
  "answered_at": null,
  "continuation_deadline": null,
  "answer": null
}
```

- `thread_id` (string or null): caller-supplied at submission (the client generates the UUID for a new thread and reuses it for every follow-up — confirmed in #54's worked example). Immutable once set. `null` means unthreaded — routing and claiming behave exactly as in v1.
- `claimed_by` (string or null): the claiming worker's `WORKER_ID` (per #54's Option A registration), set alongside `claimed_at` on **every** record, threaded or not. Purely diagnostic — it lets `bridge status` report who holds what. It is deliberately *not* load-bearing for the staleness sweep below, so nothing in this ADR depends on a worker-identity scheme that #56 has yet to formalize. This still reverses ADR-0069's "no claimant identity is stored", which held only because v1 had a single interchangeable worker.
- `continuation_deadline` (ISO 8601 timestamp or null): set on threaded records to `answered_at + 5 minutes` (the idle timeout from #54) each time the thread is answered. Consulted only by the staleness sweep, never by routing.

## Thread-aware record resolution

A record's location is now a function of its `thread_id`, so every operation that locates a record by id must take the thread into account. This is one rule, not a per-call-site patch:

> `locate(request_id, thread_id)` resolves to `queue/threads/<thread_id>/` when `thread_id` is set, and to `queue/` otherwise. `answer()`, `fail()`, and `read_answered()` all resolve through it.

Two present call sites break without this, both by looking only in top-level directories:
- `BridgeQueue.answer()` (`bridge/queue.py:83-86`) searches `self.claimed` alone, so every threaded answer would be rejected as "not claimed" and silently discarded.
- `BridgeQueue.fail()` (`bridge/queue.py:95-103`) searches top-level `claimed/` and `pending/` alone, so the capable agent's own timeout path (`server.py:69`) would fail to terminate a threaded record.

`thread_id` therefore has to reach both ends:
- **Worker side**: `_render()` (`bridge/cli.py:21-32`) emits the `thread_id` alongside the id, and `bridge answer <id> --thread <thread_id> --file <path>` carries it back. `--thread` is omitted for unthreaded requests, matching v1's invocation exactly.
- **Server side**: `server.py` already holds the record it submitted, so it passes `record["thread_id"]` to `fail()` and `read_answered()` directly.

## Staleness sweep (abandoned thread cleanup)

A crashed holder leaves `queue/threads/<thread_id>/` invisible to every other worker — nothing will ever claim its contents without a sweep. `BridgeQueue.gc()` (`bridge/queue.py:142`) gains a second pass over `queue/threads/`.

A thread is abandoned when either timestamp already in the schema has lapsed — no heartbeat file is read, so the sweep has no dependency on the per-worker `worker-<id>.alive` naming scheme that #54 sketched but no ADR has yet specified:
- a record sits in the thread's `claimed/` with `claimed_at` older than the request timeout (180s, ADR-0068 point 5) and no answer — the holder died mid-question; or
- the thread's most recent `continuation_deadline` has passed (computed as the maximum `continuation_deadline` across all records in `threads/<thread_id>/answered/`) — the holder stopped polling for follow-ups.

On either condition the sweep moves everything remaining in that thread's `pending/` and `claimed/` into its `failed/`, then writes the `.swept` tombstone. The directory itself is retained, so the thread's `answered/`/`failed/` history stays inspectable under ADR-0069's 7-day retention, while the tombstone keeps routing from ever writing into it again.

**Trigger**: `gc()` is called from the MCP tool handler in `server.py` (existing call site, `server.py:49`), *not* from `BridgeQueue.submit()`, which never calls it. Every `ask_peer_model` — and, once #57 lands, every `submit_to_peer_model` and `poll_peer_model` — therefore sweeps first. A fully quiescent bridge runs no sweep, which is harmless: the only observer that could care is a `poll_peer_model` call, and making that call is itself what fires the sweep that resolves the handle.

This deliberately does not attempt recovery: a follow-up that arrives after its thread died is answered by nobody. `poll_peer_model` (#57) returns `failed` for that handle; the capable agent may resubmit as a new thread if it still needs an answer. Answering cold, with no session context, would silently reproduce the confabulation failure the pool exists to avoid — a lost thread must be visible as lost, not papered over.

## Per-request answer staging file

`_render()` (`bridge/cli.py:21-32`) changes the staged path from the static `/tmp/bridge-answer.txt` to `/tmp/bridge-answer-<request-id>.txt`. The request id is present on every record, threaded or not, so this is a single uniform rule with no null case — no need to key on `thread_id`, which would still require a fallback for unthreaded requests. This directly removes the concurrent-overwrite race called out in #52's Notes: two workers answering in parallel now stage to distinct paths regardless of thread. The `bridge answer` subcommand deletes the staging file after writing the answer into the queue, so stale staging files do not accumulate.

## Consequences

- **No lock file, no scan-and-skip logic.** Thread exclusivity is a byproduct of where records physically live, consistent with ADR-0069's existing "directory is status" invariant rather than adding a new enforcement mechanism alongside it.
- **The global `queue.lock` is retained for thread-filtered claims, for simplicity rather than correctness.** A holding worker is the only consumer of its own `threads/<id>/pending/` by construction, so `claim_next(thread_id=...)` has no competing writer to exclude. Keeping one locking discipline for both claim paths avoids two code paths with different invariants; if pool-scale contention ever shows up in practice, dropping the lock on the filtered path is safe.
- **ADR-0071 and the installed worker prompt must be updated in step with `_render()`.** ADR-0071 §The work loop step 4 and `mcp/cline-bridge/worker-prompt.txt` both hardcode `/tmp/bridge-answer.txt`. If only `_render()` changes, the prompt tells the model to write one path while the rendered instruction submits another.
- **`bridge/cli.py`'s `answer` subcommand must accept `--thread <thread_id>`.** The thread-aware record resolution section specifies that `_render()` emits `bridge answer <id> --thread <thread_id> --file <path>` for threaded records. The subcommand must accept and pass through the `--thread` flag; without it the emitted command fails for every threaded record. This is a mandatory coordination point, not optional ergonomics.
- **Submit routing has an accepted TOCTOU with concurrent gc().** The routing check (does `threads/<thread_id>/` exist and lack `.swept`?) and the subsequent write to `threads/<thread_id>/pending/` are not atomic. If `gc()` runs in a concurrent `ask_peer_model` call between the check and the write, it could tombstone the thread directory, leaving a submitted record in an unpolled pending. This window only opens under concurrent multi-agent calls; within a single MCP handler the call to `gc()` (server.py:49) always precedes `submit()`, so the check is fresh. If a record does get written after a concurrent sweep, it is visible as failed on the caller's next `poll_peer_model` check, consistent with the ADR's "a lost thread must be visible as lost" policy.
- **`poll_peer_model` (#57) must resolve answers thread-aware.** A threaded answer lands in `queue/threads/<thread_id>/answered/<id>.json`, not top-level `queue/answered/<id>.json`. The capable agent already tracks `thread_id` per handle (#54), so it can pass it to `locate()` — a coordination point for #57, not resolved here.
- **`claimed_by` is diagnostic only.** Set uniformly on all records so the field is never present-but-meaningless, and kept out of the sweep's decision so this ADR introduces no dependency on #56's worker-identity work.
- **A swept thread cannot resume.** Intentional per the confabulation-avoidance reasoning above — resubmission as a fresh thread is the recovery path, and it is the capable agent's call whether to take it.
- **Unthreaded requests are untouched.** `thread_id: null` reproduces v1's flat `pending/claimed/answered/failed` behavior exactly; the nested `threads/` tree only exists for records that opt into it.
