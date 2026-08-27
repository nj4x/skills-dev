---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0068: Cline Bridge Loop Durability Policy

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.


**Status**: Approved

**Context**

The Cline-side worker loop (issue #41, map issue #37) runs as a single long-lived Cline task with no CLI and no outer process to restart it. Issue #44's runtime probe confirmed two unattended, unblockable ways this task dies: the 3-consecutive-mistake limit, and the model spontaneously calling `attempt_completion` — neither is gated by YOLO mode. A follow-up Explore probe of the installed fork (`cline-sr` 1.25.1, upstream base v4.0.0) confirmed a concrete restart primitive exists (`vscode://cline-sr.cline-sr/task?prompt=...`, a URI handler that creates a fresh task and self-heals a closed sidebar) and that a `TaskComplete` hook fires on `attempt_completion` but **not** on the mistake-limit abort, which exits with no hook at all. Issue #45 needed a policy for what happens when the worker dies mid-session, covering claim lifecycle, liveness detection, restart, and the capable agent's view of a dead worker.

**Decision**

1. **Claims are permanent, not leased.** A worker that claims a question and dies leaves it `claimed` forever; there is no TTL and no lease-stealing, and the question is never redelivered to a later worker. This is safe *only* combined with point 5: the capable agent's own timeout is what turns a permanently-claimed-but-dead question into an explicit terminal state, so nothing is left silently stuck.
2. **Liveness is a heartbeat, not a claim age.** `claim-next` touches a liveness-signal file on every poll, including empty-queue polls. This is the CLI's job, not the workflow prompt's, so a degrading model can't forget to do it. (File path, format, and semantics are #39's to specify; this ADR only requires that *some* on-disk signal update on every poll.)
3. **Restart is watchdog-driven, and the watchdog is defined here** because the more dangerous death mode (the mistake limit) fires no hook to drive restart any other way:
   - **Process**: a plain long-running bash loop (`bridge-watchdog.sh`), started manually once by the human alongside the worker — not itself auto-started by a Cline hook, consistent with the map's "auto-starting the worker from a Cline hook is out of scope" note extended to this second process.
   - **Prompt source**: the loop reads the canonical workflow prompt text from a fixed file on disk (path owned by #41, the loop-workflow ticket), never regenerates or embeds it inline, so the restarted task always gets the exact same instructions as the first one.
   - **Staleness threshold**: liveness signal older than 5 minutes is treated as dead. Chosen to sit comfortably above the slowest plausible normal round (~30–90s: bash timeout plus inference) so a merely-slow worker is never mistaken for a dead one.
   - **Missing liveness signal on startup**: a missing signal file is treated identically to a stale one — the watchdog fires one restart, then immediately enters the boot-grace period. This closes the startup-race window where the watchdog might fire multiple restarts before the worker writes its first heartbeat.
   - **Restart action**: `open "vscode://cline-sr.cline-sr/task?prompt=$(cat <prompt-file> | <URL-encode-utility>)"` where the exact URL-encoding utility (e.g. a Python one-liner or shell function) is an implementation detail of `bridge-watchdog.sh`, not this ADR.
   - **Boot-grace period and coupling**: after firing a restart, the loop sleeps for 2 minutes before re-checking staleness. The 2-minute grace is shorter than the 5-minute staleness threshold by design; the watchdog re-checks after 2 minutes and will find a fresh signal from the restarted worker (whose normal round time is ~30–90s), avoiding a spurious second restart. This coupling guards against independent tuning of either constant.
   - **The watchdog's own failure is an accepted single point of failure.** No meta-watchdog. If it dies, a human notices (no questions are moving) and restarts it manually — this is the simplest complete answer given the watchdog itself is a single lightweight loop with minimal failure surface.
   - **What restart buys**: nothing for the question the dead worker was holding (permanent claims mean that question is never revisited by any worker, dead or restarted) — only for every question still in the queue *after* it, which would otherwise stall forever behind a dead worker. Restart un-jams the pipeline; it does not recover the stuck question.
4. **A restarted worker carries no state beyond the queue.** No session id, no resume file, no "this is a restart" flag. Each round is designed stateless (per the prior research doc's truncation-safety guidance), so a fresh task is indistinguishable from the first one.
5. **The capable agent's `submit_request` blocks for 180 seconds, and marks the question `failed` on timeout.** 180s covers one normal worker round with margin; it is not sized around watchdog recovery, because restart cannot save this specific question (point 3). On timeout, `submit_request` itself writes the question's status to `failed` before returning an error to its caller — this is what makes point 1 safe: a claimed-forever question becomes an explicit terminal state within 180s of any death, mistake-limit or `attempt_completion` alike, with no asymmetric handling needed between the two death modes. (A late answer arriving after the status was marked `failed` is discarded; this is a rare race, not a design gap.)
6. **The bridge is single-question, blocking-response**, per #40's expected interface: `submit_request` returns `{status, answer}` directly — no polling handshake, no webhook, no follow-up threading. This ADR assumes that shape to size the 180s timeout in point 5; the interface itself is #40's decision. Threading is out of scope for v1 (map issue #37's "Not yet specified").
7. **Queue payloads are inert text**, per #46: this ADR assumes queue text is processed as literal prompt/answer content on both sides, never evaluated as a shell command — the trust-boundary decision itself belongs to #46.

**Consequences**

- Point 3's watchdog is now a load-bearing, fully external process with no supervision of its own; if the human never starts it, or it crashes, every worker death degrades to "the capable agent times out and marks the question failed, but nothing un-jams the *next* question" — i.e. the queue silently stops making progress beyond one failed question, indistinguishable from the worker being merely slow until a human checks. A running watchdog is an operational precondition for this ADR's durability guarantees, not an optional nicety.
- Removing the `attempts`-counter/`TaskComplete`-hook mechanism (present in an earlier draft) in favor of point 5's uniform failed-on-timeout marking is a deliberate simplification: under permanent claims (point 1), a question is attempted exactly once by construction, so a per-question retry counter had no work left to do once the capable side marks failure directly. One mechanism now covers both death modes instead of two asymmetric ones.
- Retention/GC of `failed` and `answered` records, and the exact schema fields (heartbeat file format, status enum, etc.), are #39's to specify; this ADR only requires that a `failed` state exists and is reachable as described in point 5.
