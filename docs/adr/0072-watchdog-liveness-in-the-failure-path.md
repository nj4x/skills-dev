---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0072: Watchdog Liveness in the ask_peer_model Failure Path

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

Amended by ADR-0079: the watchdog is opt-in rather than the default posture, and an absent
watchdog now reads as "assume the pool is live" instead of gating the call. The `watchdog`
field described below is dropped — under that flip `worker_offline` is reachable only when the
watchdog is alive, so the field could only ever hold `"alive"`. Everything here still describes
how the watchdog reports itself while it is running.

**Context**

Issue #48 verified that `bridge-watchdog.sh` restarts a dead worker, which took the human out of the worker-death path entirely: a dead worker self-heals within 330 seconds worst case with nobody watching. ADR-0068 point 3 accepted the watchdog as an unsupervised single point of failure on the reasoning that "a human notices (no questions are moving)" — but after #48 that reasoning no longer holds. Worker deaths no longer stall the queue, so there is nothing for a human to notice. When the watchdog itself dies, the system looks healthy right up until the next worker death, and then stalls indefinitely.

`bridge status` reported only `worker=alive|offline`, which says nothing about whether anything is left to restart the worker when it next dies. Issue #49 decided the shape; issue #51 implements it.

**Decision**

## Watchdog liveness is a second heartbeat, not a process check

`bridge-watchdog.sh` touches `watchdog.alive` in the bridge root — sibling of the worker's `worker.alive` — on every check-interval iteration, including the startup check before any restart decision. `pgrep -f bridge-watchdog.sh` was the alternative; it is a fine operator check from a shell but is not reachable from the MCP server's answer to the calling model, and it reports a *process* rather than a *loop that is still iterating*. A hung watchdog still has a pid.

## One staleness threshold for both heartbeats

`STALE_HEARTBEAT_SECONDS = 300` covers watchdog staleness as well as worker staleness. No second constant. A healthy watchdog's longest silence is 150 seconds — the 120-second boot grace after firing a restart plus one 30-second check interval — so 300 leaves 150 seconds of margin, and a single constant cannot drift out of coupling with the other.

## The fact is surfaced as a sibling field, not a new reason

When `ask_peer_model` returns `{status: "failed", reason: "worker_offline"}` it now carries a fourth field, `watchdog: "alive" | "offline"`. The two facts are orthogonal: `reason` answers *why this call failed*, `watchdog` answers *whether the next call will fail the same way*. Folding them into one enum would multiply reasons combinatorially for no gain.

This amends ADR-0070's output shape, which fixed the return at `{id, status, answer, reason}`. That ADR's `reason` enum is unchanged and still has exactly three values (`timeout`, `worker_offline`, `queue_unavailable`); `watchdog` appears only on the `worker_offline` result, where it is the only place it carries information — on `timeout` the worker was demonstrably alive at submission, and on `queue_unavailable` the filesystem is the problem.

## `bridge status` reports both

The CLI prints `watchdog=alive|offline` under `worker=alive|offline`, so the human debugging the queue sees the same distinction the calling model sees.

## The watchdog stays unsupervised

No meta-watchdog, per ADR-0068 point 3. This ADR amends only the *reasoning* behind that acceptance, not the acceptance itself: watchdog death is now detected and reported rather than inferred from an absence of progress. Recovery from it remains manual — a documented `nohup ./bridge-watchdog.sh &` in the README.

**Consequences**

- A calling model that gets `worker_offline` can now tell "wait and retry, a restart is due" from "escalate to the human, nothing is coming". `engineering/ask-peer-model/SKILL.md` documents both branches.
- The window in which a dead watchdog is invisible shrinks from unbounded to 300 seconds — but only *once someone asks a question*. Nothing polls; the report is pull-only, so a fully idle bridge with a dead watchdog still looks like nothing at all. This is deliberate: the only observer that matters is a caller, and a caller learns the truth on its first call.
- Two heartbeat files now exist under one root. The watchdog writes its own directly in bash rather than through the `bridge` CLI, so the file path is duplicated between `bridge-watchdog.sh` and `bridge/queue.py` — the same duplication `worker.alive` already carries, and the same one that produced the split-brain caught in issue #50. Both derive from `CLINE_BRIDGE_DIR` with matching tilde expansion.
