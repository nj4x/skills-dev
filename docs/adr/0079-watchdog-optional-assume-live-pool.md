---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0079: The Watchdog Is Optional and an Absent One Means "Assume Live"

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

`worker-N.alive` is touched in exactly two places, both inside the `bridge` CLI: at the top of
every `claim-next` poll and once per `answer`. Nothing else refreshes it. A worker that has
claimed a hard question therefore stops touching its heartbeat for as long as the answer takes
— reading files, running commands, writing the answer — and `STALE_HEARTBEAT_SECONDS` is 300
while the async budget for a single question is 1800. **A busy worker and a dead worker are the
same reading.** The heartbeat records "recently polled", not "alive".

That inaccuracy was tolerable while something acted on it. `bridge-watchdog.sh` is that
something: it restarts a stale slot, so a false positive costs one spurious restart. But it also
makes the false positive expensive in a way ADR-0074 did not anticipate — the restart opens a
new Cline task via a `vscode://` URI without killing the old one, and the replacement claims the
same slot the busy worker still holds. Two tasks then poll one queue under one slot number.
`docs/research/cline-worker-premature-completion.md` traces the 2026-08-28 double-worker
incident to exactly this.

Meanwhile `pool_alive()` had one consumer outside tests: the pre-flight gate in
`ask_peer_model` that refuses to enqueue when no slot is fresh. With no watchdog running, a
stale heartbeat is a reading nobody will ever act on — and the gate turns it into a refusal of a
question a working pool would have answered.

ADR-0072 built the `watchdog: "alive" | "offline"` field on the assumption that the watchdog is
always meant to be running and its absence is a fault to report. In practice it is a tool worth
reaching for deliberately, and running it by default costs more than it returns.

**Decision**

## The watchdog is opt-in, not the default posture

The README's round trip no longer starts with the watchdog. Workers are started on their own,
and the watchdog is a documented extra for when unattended self-healing is worth its
restart-collision risk. ADR-0068 point 3 and ADR-0072 both still hold for the case where it
*is* running; this ADR changes only whether that case is the default.

## An absent watchdog means "assume live"

`pool_alive()` is replaced by `pool_offline()`, which is true only when the watchdog is alive
*and* no slot is fresh:

```python
return self.watchdog_alive() and not any(alive for _, alive in self.worker_slots())
```

Staleness is acted on only by the component that can act on it. With no watchdog, the pool is
assumed live and the question is enqueued; a pool that is genuinely down then surfaces as
`timeout` after the full block rather than as an instant refusal. The alternative — keeping the
gate unconditional — was rejected because its failure mode is silent and wrong (refusing a
working pool) while the new one is merely slow and correct.

`claim_worker_slot` keeps using heartbeat freshness unchanged. It asks a different question —
"is this slot taken" — and assuming a slot live there would make every slot permanently
occupied and no worker could ever start.

## The `watchdog` field is dropped from the result

Under the flip, `worker_offline` is reachable only when the watchdog is alive, so ADR-0072's
sibling field would be the constant `"alive"` on every result that carries it. A field that
cannot vary carries no information. Its meaning — *a restart is already due, wait and retry
once* — folds into the documented meaning of `worker_offline` itself.

This amends ADR-0072, which added the field, and restores ADR-0070's `{id, status, answer,
reason}` shape exactly. The `reason` enum is unchanged and still has three values.

**Consequences**

- The restart-collision path is off by default. Two Cline tasks can no longer end up on one
  slot without the operator having chosen to run the watchdog.
- `ask_peer_model` loses its fast-fail when nothing at all is running: the caller waits the full
  `CLINE_BRIDGE_TIMEOUT` (180s default) and gets `timeout`. This is the price of the flip and is
  paid once per session in practice, since the human notices at the first question.
  `engineering/ask-peer-model/SKILL.md` tells the calling model to read a first-question
  `timeout` as "check a worker is up" rather than "the worker is thinking".
- `pool.conf` is unwritten by default, so the slot ceiling falls back to `MAX_POOL_SIZE` (10)
  per `pool_size()`. The ceiling was only ever a guard against a runaway pool, and a human
  opening VS Code windows by hand is not that.
- `bridge status` is unchanged: it still reports per-slot `alive|offline` and `watchdog=`. It is
  the operator's view of the raw facts, and the flip is about what the *server* infers from
  them, not about hiding them.
- The heartbeat remains a "recently polled" signal misnamed as liveness. This ADR narrows the
  blast radius of that imprecision rather than fixing it; a heartbeat touched by a background
  timer for the duration of an answer would fix it properly and is not attempted here.
