---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0074: Worker Pool Identity, Registration, and Lifecycle

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Known Risks (Accepted)**

This ADR accepts five known risks that are documented here rather than blocked:

1. **`worker_offline` aggregation contract is unspecified.** The ADR redefines `worker_offline` (pool-wide failure) but does not specify how `ask_peer_model` aggregates per-worker `bridge status` lines into a single tool enum. An implementation that looks for the old single `worker=offline` line will find no match in the new format and may always return alive, silently masking a dead pool. **Mitigation**: ticket #56's implementation work must specify the aggregation contract; the ADR sketches the semantic change only.

2. **Deliberate pool shrinkage has no teardown path.** The watchdog monitors "heartbeat files that exist and have gone stale" without distinguishing human-intentional closure from crash. A human closing window 3 (to shrink from N=3 to N=2) leaves `worker-3.alive` stale after 300s, triggering a restart URI that lands in an arbitrary window per the misdirected-restart consequence, killing a live claim. **Mitigation**: declared out-of-scope for the watchdog — human must either (a) stop the watchdog before closing windows, or (b) manually remove the worker-N.alive file to prevent spurious restarts.

3. **`pool.conf` is absent if the watchdog doesn't start first.** The slot-ceiling enforcement depends on reading `pool.conf`, which the watchdog writes. If a worker starts before the watchdog, the file is absent and the ceiling is unenforceable. **Mitigation**: documented startup ordering constraint — start watchdog before opening windows.

4. **The "20 seconds apart" restart gap has no formal definition.** The claim that sequential restarts spaced 20s apart prevent concurrent window overwrites carries no source or configuration constant, and fails if Cline task startup time exceeds the gap. **Mitigation**: the restart gap is a tunable parameter that ticket #56 implementation must define formally; the ADR documents the structure only.

5. **Stale heartbeat is not cleared after restart, risking cascading restarts.** When a worker is restarted it may claim a different slot N' than the one that triggered the restart; the original stale `worker-N.alive` remains, firing another restart on the next poll. **Mitigation**: the watchdog implementation (ticket #56) should add a grace period after firing a restart, skipping that slot on the next poll.

**Context**

Map issue #52 extends the bridge to a pool of 2–3 Cline workers. ADR-0068 sized every liveness
decision around exactly one worker: a single `worker.alive` heartbeat, a single
`bridge-watchdog.sh` loop, and a single restart primitive
(`open "vscode://cline-sr.cline-sr/task?prompt=..."`). Ticket #54 sketched per-worker heartbeat
files and a `WORKER_ID` but left the mechanism unspecified. Ticket #56 settles it.

The shape of the answer is forced by how Cline's restart primitive resolves its target. In the
upstream source the `/task` URI handler dispatches to `WebviewProvider.getVisibleInstance()`, and
`WebviewProvider` holds a single static `instance` field per extension host
(`src/core/webview/WebviewProvider.ts:12`, `src/services/uri/SharedUriHandler.ts`). One VS Code
window therefore has one Cline task slot, and the URI carries no way to address one window among
several. The installed extension is the `cline-sr` fork (base v4.0.0 per ADR-0068) rather than
upstream, so this is inference rather than direct observation of the deployed build — but a
webview singleton is core architecture, not rebrand configuration. Upstream additionally publishes
a standalone `cline` CLI (`cli/cline.rb`); the fork does not, which is the reason this bridge
exists at all.

**Decision**

## A worker is a VS Code window, and the pool is opened by hand

N workers means N VS Code windows, each its own extension host process, each running one Cline
task against the shared queue root. There is no headless worker and no second task inside one
window. The human opens the windows; nothing auto-starts them, consistent with map #52's
"auto-starting workers from a hook is out of scope".

## Workers claim a slot at startup

The human sets `POOL_SIZE` (an integer, 1 ≤ POOL_SIZE ≤ 10) in the watchdog's environment. There
is no per-worker `WORKER_ID` assigned at launch. Instead, each Cline task calls
`bridge claim-worker-slot` at startup, which:

1. Takes the queue lock.
2. Globs `~/.cline-bridge/worker-*.alive` (under lock, to avoid stale results between the glob
   and the slot-assignment write).
3. Finds the lowest slot N (1 ≤ N ≤ POOL_SIZE) whose `worker-N.alive` is absent or older than
   `STALE_HEARTBEAT_SECONDS`.
4. Touches `worker-N.alive`.
5. Releases the lock.
6. Returns N to the caller.
7. If no slot is available (all POOL_SIZE heartbeat files are fresh), the command exits non-zero
   with a slot-full error. The Cline task must handle this error by surfacing it to the user rather
   than proceeding without a slot assignment.

The watchdog writes POOL_SIZE to `~/.cline-bridge/pool.conf` at startup; `bridge claim-worker-slot`
reads this file to enforce the slot ceiling.

The worker then passes N to all subsequent CLI invocations (e.g., `bridge claim-next --worker 1`).
This keeps the worker — the only process running inside VS Code — as the entity writing its own
heartbeat, preserving ADR-0068 point 2 ("liveness is the CLI's job"). No hostname, no pid, no
uuid: the pool is small and a generated id would have no reader that a slot integer does not serve.
`BridgeQueue` gains the per-worker heartbeat path in place of the fixed one, and `bridge status`
reports liveness per worker by globbing `worker-*.alive`.

## Registration is heartbeat-file discovery; pool size is env-var configuration

Workers are discovered by their heartbeat files. Nothing declares a roster, nothing de-registers,
and a worker that stops touching its file simply goes stale. A manifest was rejected because it
would add write, cleanup, and de-registration machinery — and a new race between registration and
crash — to serve a purely diagnostic view. An env-var pool count is accepted as sufficient because
the human already supplies it manually when opening the windows.

This holds because worker identity has no load-bearing consumer. ADR-0073 deliberately kept
`claimed_by` diagnostic and drove the abandoned-thread sweep off `claimed_at` and
`continuation_deadline` alone, reading no heartbeat at all. So identity feeds `bridge status` and
the watchdog's restart decision, and nothing else.

Consequently ticket #56's original question "how long before a dead worker's thread is released?"
has no answer *here*: thread release is timestamp-driven in ADR-0073 and is independent of whether
the holder's heartbeat has gone stale.

## One watchdog loop monitors heartbeat files that exist; POOL_SIZE is a ceiling, not a launch directive

`bridge-watchdog.sh` stays a single process, started once by hand
(`nohup ./bridge-watchdog.sh &`), and polls every 60 seconds for heartbeat files that exist and
have gone stale. It restarts stale workers individually; workers are already independent by
construction (separate claim path, separate heartbeat), so a shared scan loop needs no coordination
between them. N watchdog processes were the alternative and were rejected: they multiply the
unsupervised single point of failure that ADR-0068 point 3 accepted exactly once, for no gain in
isolation.

The watchdog does NOT preemptively start workers based on POOL_SIZE. The human opens N windows
(N ≤ POOL_SIZE); each worker claims its own slot at startup via `bridge claim-worker-slot`. The
watchdog then monitors only the heartbeat files that exist. POOL_SIZE is a lease ceiling — a
limit on how many simultaneous workers the queue will accept — not a directive to the watchdog to
start that many. On startup, zero heartbeat files exist, so the watchdog fires no startup restarts
until the human opens windows and they claim slots.

The watchdog keeps its own `watchdog.alive` heartbeat unchanged (ADR-0072) — one watchdog, one
liveness file — and `STALE_HEARTBEAT_SECONDS = 300` applies per worker, unchanged from ADR-0068.
Pool size does not change how long a silent worker is tolerated.

## One shared worker prompt

All workers read the same `~/.cline-bridge/worker-prompt.txt`, gaining one sentence stating that
the worker is one of several in a pool. The prompt does not name the worker's slot — that is
discovered at runtime by `bridge claim-worker-slot`. No per-worker prompt files and no prompt
generation: every worker's instructions are otherwise identical, and ADR-0068 point 3 requires the
restart to replay the canonical prompt text verbatim.

**Consequences**

- **The restart primitive cannot target a specific window, and the watchdog has no way around
  it.** `open vscode://...` hands off to whichever Cline webview the OS considers visible. With
  several windows open, a restart fired for worker N may land in a different window — killing a
  live claim (permanent under ADR-0068 point 1, so that question is lost, recoverable only by the
  caller's 180s timeout) while the intended worker stays dead. A misdirected restart occurs when
  the `open vscode://...` URI lands in a window other than the intended one; the exact rate depends
  on macOS window focus order at restart time, which is deterministic and unknown to the watchdog.
  Each misdirected restart costs one lost live claim. Restarts are sequential; if N workers'
  heartbeats go stale within one check interval, they are restarted 20 seconds apart, so no window
  is overwritten twice before claiming a slot. A restarted worker claims its slot before the next
  restart fires. This is the pool's sharpest known weakness. It is accepted rather than solved
  because no addressing mechanism exists in the fork. The mitigation is operational: keep the pool
  small, observe `bridge status` after unattended restarts, and account for the cost in
  operational budget (one lost claim per misdirected restart).
  If misdirected restarts prove common in practice, the fix is a per-worker restart primitive in
  the fork, not more watchdog logic.
- **`bridge status` output grows a line per worker.** The single `worker=alive|offline` line
  becomes one per discovered heartbeat file. Each per-worker line is `worker-N=alive|offline`
  where N is the slot number parsed from the heartbeat filename. Lines are printed in ascending
  slot order; a single-worker pool produces exactly `worker-1=alive|offline`. ADR-0072's
  `watchdog=alive|offline` line is unaffected. The `worker_offline` reason returned by `ask_peer_model` now means *no worker in the
  pool is alive*, not *the worker is not alive*. Consumers of `worker_offline` are: (1)
  `ask_peer_model` tool, which must treat it as pool-wide failure, not single-worker failure; (2)
  bridge status parsers, which must iterate per worker to show partial pool degradation; (3)
  ask-peer-model skill, which already handles pool-wide failure via the tool's return. Behavioral
  changes to (1) and (2) are in scope for ticket #56; (3) requires no change.
- **The pool size lives in the watchdog's environment as POOL_SIZE.** The watchdog scans
  heartbeat files that exist and restarts any older than `STALE_HEARTBEAT_SECONDS`. POOL_SIZE is
  a ceiling only — it bounds how many simultaneous workers the queue will accept claims from, but
  does not direct the watchdog to start workers preemptively. This is configuration the human
  already supplies when opening the windows, not state the system maintains — nothing writes it,
  nothing reconciles it.
- **`worker.alive` from v1 is replaced, not kept alongside.** A single-worker setup is the pool
  with N=1 and heartbeats to `worker-1.alive`; `bridge-watchdog.sh` and `bridge/queue.py` must
  change in step, the same coupling ADR-0072 flagged between those two files. Run
  `mv ~/.cline-bridge/worker.alive ~/.cline-bridge/worker-1.alive` before upgrading.
  bridge-watchdog.sh and bridge/queue.py must be updated in step (same coupling as ADR-0072
  §Consequences); starting the new watchdog against the old queue.py, or vice versa, produces a
  split-brain where one side scans worker-1.alive and the other scans worker.alive.
- **The `claimed_by` field in ADR-0073's queue records is now a slot assignment, not durable
  worker identity.** Both this ADR and ADR-0073 call it diagnostic-only; it now means "which slot
  held this claim" rather than "which worker ID held this claim." A slot number is stable within a
  single run (1..POOL_SIZE), but not across restarts (a restarted task may claim a different slot
  if another slot becomes free). Thread release in ADR-0073 ignores heartbeats entirely and drives
  off `claimed_at` and `continuation_deadline`, so this semantic shift is not load-bearing.
- **The heartbeat signal's role is watchdog restart decision and pool-scale observation,
  not thread release.** When a slot's heartbeat goes stale, the watchdog fires a restart; when a
  slot has no heartbeat file, it appears offline in `bridge status`. Neither of these signals
  drives thread release — that is timestamp-driven in ADR-0073 off `claimed_at` and
  `continuation_deadline` alone. The heartbeat is not load-bearing for thread safety.
