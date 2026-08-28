---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0077: Thread-Bound Worker Loop

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

ADR-0073 shipped the queue side of thread binding and ADR-0076 the async surface that creates
threads, but nothing told the worker to use either. ADR-0071 §The work loop, `worker-prompt.txt`,
and `.clinerules/bridge-trust-boundary.md` all described one unfiltered loop: claim, answer, claim
again. Thread ownership is directory location — unfiltered `claim-next` scans only top-level
`pending/`, so a follow-up submitted into `threads/<id>/pending/` is reachable *only* through
`claim-next --thread <id>`. A worker that answered a thread's first message and went straight back
to the plain poll left every follow-up unreachable until `gc()` failed it with `thread_abandoned`,
five minutes later.

Three questions had to be settled: how the worker knows when to leave a thread, whether leaving is
safe before the thread is tombstoned, and whether the instruction belongs in the prompt or in CLI
output.

**Decision**

## The worker holds no state; every command names the next one

The worker keeps no counter and no timer. `bridge answer` on a threaded record ends by printing
`bridge claim-next --worker N --thread <id> --wait 25`; an empty thread poll prints either that same
command again or `THREAD CLOSED`, which prints the unfiltered poll. The prompt is reduced to one
rule — *run the command the last output printed, verbatim* — and carries no branch of its own.

The deadline arithmetic lives in the CLI, which reads `continuation_deadline` off the thread's
answered records. This follows ADR-0071's §No pacing sleep reasoning: tool output is re-read on the
turn it matters, so a load-bearing instruction placed there survives context truncation, while
prompt text competes with everything else in a long window. Expressing a five-minute idle window as
"about twelve empty polls" would have required the model to maintain a count across turns — the one
thing this design has consistently failed to make reliable.

## The departing worker writes the tombstone

Leaving a thread before `.swept` exists is **not** safe, so the CLI writes the tombstone at the
moment it tells the worker to go. `BridgeQueue.close_thread_if_idle(thread_id)` fires on an empty
thread poll whose continuation deadline has lapsed. `submit()` already routes into top-level
`pending/` when `.swept` is present, so a follow-up arriving after departure lands in the unfiltered
queue and any worker takes it — as a fresh first message, without the thread's session context,
which is the honest meaning of the thread having gone idle. Nothing is stranded and nothing is
failed with `thread_abandoned`.

The close runs under the queue lock and **refuses to fire while the thread's `pending/` holds
anything**, so a follow-up racing the close wins: the worker polls once more and claims it. This is
the one ordering that avoids both the strand and a spurious failure.

`gc()`'s own sweep is unchanged and remains the path for a thread whose worker died before it could
close.

**Consequences**

- One worker in the pool is off the shared queue for the length of a thread's idle window. That is
  the cost of Option C thread binding (issue #54) and is accepted; the remaining slots cover
  top-level work.
- A thread reopened after close degrades to unthreaded behaviour permanently — `.swept` is never
  removed, so every later message in that thread id goes top-level. Acceptable: the caller-side
  contract is that a thread is live only within its idle window.
- Changes to `worker-prompt.txt` carry ADR-0071's redeployment cost: update the repo copy, re-run
  the install step that copies it to `~/.cline-bridge/worker-prompt.txt`, restart the Cline task.
