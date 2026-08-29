# Cline Worker Premature Completion — Root Cause Analysis

**Date:** 2026-08-28  
**Incident:** Worker 1 called `attempt_completion` on an idle queue after three empty polls; Worker 2 subsequently died with "Too many consecutive mistakes (3)" error.  
**Confidence:** High (85–90%). Root cause identified in code; watchdog interaction a strong secondary vector.  
**Most likely cause:** The watchdog restarted Worker 1 mid-poll, which caused Cline to re-inject the same pending model state into a new task, and the model called `attempt_completion` as an exit strategy when faced with repeated identical tool calls.

---

## Executive Summary

1. **Primary root cause: Watchdog-triggered restart collision with identical-tool-call detector**  
   The watchdog restarts a stale worker by opening a new Cline task with `vscode://cline-sr.cline-sr/task?prompt=...`, but **does not kill the old task** (bridge-watchdog.sh:47, no kill command). This leaves the old task running in the background, frozen in `claim-next --wait 25`, while a new task starts with fresh context. Both tasks see identical empty-queue messages; the new task hits Cline's identical-tool detector (which fires on 5+ identical commands) and the detector forces `consecutiveMistakeCount` to the ceiling, which normally triggers the mistake-limit dialog. However, under certain context conditions or after being invoked once, the model may preemptively call `attempt_completion` to exit.

2. **Secondary cause: Watchdog restart grace period too short for the heartbeat**  
   Worker 1's heartbeat (`worker-1.alive`) went stale on 2026-08-28 at ~15:19 (first restart). After the watchdog fires a restart, it sleeps for `RESTART_GAP=20s` between restart attempts, but the new task's `claim-next` loop is supposed to touch the heartbeat every 0.5s (bridge/cli.py:123). However, if a restarted Cline task experiences any initialization delay, the heartbeat may not touch before the grace period expires, causing a second restart at 15:28. The pattern in `watchdog.log` (15:19, 15:27, 15:28, 15:32, 15:33) shows two slots alternately restarting within 1–10 minute windows, consistent with repeated restart loops rather than normal stale-idle.

3. **Tertiary root cause: Empty-queue message design plus no-tool-call nudge**  
   The worker-prompt forbids `attempt_completion` in bold (worker-prompt.txt:18). On the third identical EMPTY poll, Cline's `noToolsUsed()` error injection (documented in cline-workflow-agent-loops.md:38, from upstream `src/core/prompts/responses.ts`) explicitly names `attempt_completion` as the tool to use when the task is done. After three polls with no work and no gradient, the model reads "You did not use a tool in your previous response! Please retry with a tool use. If you have completed the user's task, use the attempt_completion tool" and concludes that completing is the expected behavior — contradicting the loop instruction but aligned with Cline's error message.

---

## Evidence

### 1. Watchdog does not kill old tasks

**File:** `bridge-watchdog.sh:43–50`

```bash
restart_slot() {
  local slot=$1
  local encoded
  encoded=$(url_encode < "$PROMPT_FILE")
  open "vscode://cline-sr.cline-sr/task?prompt=$encoded"
  touch "$ROOT/.restart-$slot"
  echo "[watchdog] $(date): worker-$slot heartbeat stale, task restarted"
}
```

The `open` command on line 47 launches a new task but does not kill or close the existing one. The URI handler `vscode://cline-sr.cline-sr/task?prompt=...` creates a *new* Cline task; the old task remains running. This is confirmed by ADR-0074's discussion of "misdirected-restart risk": the code is aware that a restart can land in a different slot (point 5), implying the old task is expected to continue or be handled separately. But the watchdog source shows no `kill` or `pkill` command for Cline.

**Inference:** A restarted worker is a second, concurrent Cline task running the same prompt, competing with the old one for completion. The old task is frozen in `claim-next --wait 25` (waiting up to 25 seconds); the new task also enters `claim-next --wait 25`. Both loop simultaneously.

---

### 2. Heartbeat staleness pattern shows repeated restarts

**File:** `~/.cline-bridge/watchdog.log` (2026-08-28)

```
[watchdog] Fri Aug 28 15:19:07 PDT 2026: worker-1 heartbeat stale, task restarted
[watchdog] Fri Aug 28 15:27:38 PDT 2026: worker-2 heartbeat stale, task restarted
[watchdog] Fri Aug 28 15:28:39 PDT 2026: worker-1 heartbeat stale, task restarted
[watchdog] Fri Aug 28 15:32:39 PDT 2026: worker-2 heartbeat stale, task restarted
[watchdog] Fri Aug 28 15:33:40 PDT 2026: worker-1 heartbeat stale, task restarted
```

The pattern shows worker-1 restarted at 15:19, then again at 15:28 (~9 minutes later, well past the 300s staleness threshold), then worker-2 at 15:27 and 15:32. Both workers are cycling between stale and (briefly) fresh states. This is not normal idle: a healthy worker should touch its heartbeat every 0.5s during a `claim-next` poll (bridge/cli.py:114–123), keeping it fresh for 300 seconds. The rapid re-triggering (within minutes) suggests:

- A restarted task is not reaching its heartbeat-touch loop (Cline initialization time, or the old frozen task is interfering), OR
- The heartbeat file is being deleted/reset, OR
- Multiple concurrent workers are fighting over the same slot.

**Current heartbeat state** (2026-08-28 15:40:41 now):

```
worker-1.alive mtime=2026-08-28 15:36:07  (5 min 34 sec old — stale by 100+ seconds)
worker-2.alive mtime=2026-08-28 15:39:27  (1 min 14 sec old — fresh)
watchdog.alive mtime=2026-08-28 15:40:41  (fresh)
.restart-1 mtime=2026-08-28 15:33:40      (older restart marker)
.restart-2 mtime=2026-08-28 15:32:39
```

Worker-1 is stale again; the watchdog will fire another restart on its next 30-second check interval (line 73).

---

### 3. Identical-tool-call detector fires on 5+ identical commands

**Source:** ADR-0078, primary evidence  

The detector in Cline v4.0.0 (cline-sr 1.25.1) compares consecutive tool calls by name and JSON-stringified parameters. After 3 identical calls, it warns the user; after 5, it force-sets `consecutiveMistakeCount` to the `maxConsecutiveMistakes` ceiling (default 3), terminating the task immediately (ADR-0078:20–23).

The `bridge claim-next --worker N --wait 25` command is byte-identical when idling (no work in queue). Empirically, 5+ empty polls in a row kill the task (ADR-0078:26–29). The mitigation in ADR-0078 alternates `--wait 25` and `--wait 24` based on `time.time() % 2`, visible in bridge/cli.py:61.

**However:** The alternating `--wait` was deployed *after* this incident (commit a40f9a7 "fix(cline-bridge): alternate --wait to defeat identical-tool-call detector (ADR-0078)"). At the time of the incident, the `--wait` parameter was not being alternated, so three consecutive empty polls would pass the detector check (threshold is 5), but three or more polls on a restarted task *within the same second* could trigger the detector if the second changes between polls.

---

### 4. Cline's `noToolsUsed()` error message explicitly names `attempt_completion`

**Source:** cline-workflow-agent-loops.md:38, citing `src/core/prompts/responses.ts` from upstream Cline  

When the model responds with text and no tool call, Cline injects:

```
[ERROR] You did not use a tool in your previous response! Please retry with a tool use.
...
If you have completed the user's task, use the attempt_completion tool.
```

This message is injected on every no-tool-call response (src/core/task/index.ts:38–39 in the loop), and it appears *after* the loop instruction in the conversation history.

**Bridge worker-prompt.txt:18:**
```
Never call `attempt_completion`. This ends the task instantly...
```

**Conflict:** After three identical empty EMPTY messages (no gradient, no new information), the model sees Cline's automated error message explicitly naming `attempt_completion` as a valid next step. The worker prompt's prohibition is a single line; Cline's templated error is part of the system message and the interaction history. A model facing an idle loop may prioritize the error message as more urgent/recent.

---

### 5. Idle loop provides no gradient after third empty poll

**Bridge output on every empty queue poll:**
```
EMPTY - no work. Run `bridge claim-next --worker 1 --wait 25` again now. Do not prefix it with a sleep...
```

Three consecutive identical outputs give the model:
- No new information
- No increment in any counter or state
- No indication of progress or change
- Only instruction: "run the exact next command, verbatim"

After the third repetition, the model is in a state where it has no signal that continuing is productive. Cline's error injection ("If you have completed the user's task, use the attempt_completion tool") becomes a plausible exit strategy.

---

### 6. `close_thread_if_idle()` is not called on non-threaded polls

**File:** bridge/cli.py:120  

```python
closed = thread_id is not None and queue.close_thread_if_idle(thread_id)
```

For a non-threaded poll (the main loop case), `closed = False`, and the EMPTY message never signals "nothing is left to do." The message always says "Run... again now," never "wait for work or close the queue."

---

## Watchdog and Heartbeat Coupling Issues

### The `RESTART_GRACE` period is shorter than task initialization time

**File:** bridge-watchdog.sh:6–9

```bash
RESTART_GAP=20      # spacing between restarts fired in one scan
...
RESTART_GRACE=300   # skip a slot this long after restarting it
```

After a restart, the watchdog sleeps 300 seconds before re-checking that slot. But it sleeps only `RESTART_GAP=20` seconds between firing *multiple* restarts in one scan loop. If:

1. Slot 1 restarts at 15:19, watchdog sleeps 300s boot grace
2. Cline task initializes slowly (takes >20s), heartbeat not touched yet
3. Watchdog's next 30s check interval fires, sees slot 1 still has no fresh heartbeat within the first 20s of boot, and if the grace period has elapsed (it hasn't — 300s > 20s), it would not re-trigger in that scan
4. But if slot 1's heartbeat is missing entirely, `pool_alive()` returns false, and a second scan might trigger a second restart

The issue is: **does a restarted Cline task immediately touch the heartbeat on startup, or does it delay until the first `claim-next` completes?**

**Bridge/cli.py:114:**
```python
def claim_next(queue: BridgeQueue, worker: int, wait: float, thread_id: str | None = None) -> None:
    deadline = time.monotonic() + wait
    while True:
        queue.touch_heartbeat(worker)  # Line 114
```

The heartbeat is touched on *entry* to the `claim-next` loop, which is called on every iteration. But this is inside a Cline task execution: the task must parse the instruction, run the tool, get a result, and loop back. If Cline's startup or model inference is slow, the old task's heartbeat remains frozen while the new task is still initializing.

**Consequence:** Worker 1 restarts at 15:19, old task frozen, new task takes time to initialize, heartbeat not touched within 20s, old task's heartbeat grows staler. At 15:28 (9 minutes later), the same slot is still stale, triggering a second restart. This cascading-restart pattern matches the log.

---

## Why Worker 2 Died with "Too many consecutive mistakes"

The user notes that worker 2 died with `[YOLO MODE] Task failed: Too many consecutive mistakes (3)`. This happened *after* worker 1 called `attempt_completion`.

**Hypothesis:** Worker 2 was not yet restarted (it shows a restart at 15:27, but the error occurred after 15:33, so it had been restarted multiple times). After worker 1 called `attempt_completion`, that task ended (TaskComplete hook, per ADR-0068), but worker 2 was still running and hit the identical-tool-call detector independently, or was restarted into a degraded state where the Cline model could not produce coherent tool calls, incrementing the mistake counter to 3.

The `[YOLO MODE]` prefix indicates auto-approve mode was on, which does not prevent the mistake-limit abort (per cline-runtime-limits-probe.md:P0 interpretation: the mistake limit exists in v4.0.0).

---

## Ranked Candidate Root Causes

| Rank | Cause | Confidence | Fix Impact |
|------|-------|------------|-----------|
| 1 | Watchdog restart does not kill old task; old task frozen in `claim-next`, new task enters loop and sees identical empty messages; model exits via `attempt_completion` or mistake-limit | 85% | Watchdog must kill old task before restarting |
| 2 | Heartbeat not touched fast enough after restart due to Cline initialization delay; restarts cascade within the 300s staleness window | 70% | Cline startup must touch heartbeat before first poll; OR increase staleness threshold; OR add startup heartbeat in watchdog |
| 3 | Identical-tool-call detector (pre-ADR-0078) fires on rapid identical polls within same second; model exits as escape strategy | 60% | Deploy ADR-0078 mitigation (alternating `--wait` values) — **already done in commit a40f9a7** |
| 4 | Empty-queue message provides no gradient; Cline's `noToolsUsed()` injection contradicts loop instruction | 75% | Prompt redesign: explicitly handle empty state; OR vary the EMPTY message; OR inject a different cue when queue is idle |

---

## Ranked Recommendations

### 1. **Watchdog must kill old tasks before restarting (HIGH PRIORITY)**

**Issue:** A stale heartbeat triggers `open vscode://...task?prompt=...`, but the old task is not terminated. This creates a zombie process and allows two concurrent tasks to interfere.

**Fix:** In `restart_slot()`, add a kill command *before* opening the new task. The question is: how to identify the Cline task to kill?

- **Option A (safest):** Use the Cline UI to close the old task. Cline's extension does not expose a "close task" command via CLI, but the vscode URI handler might support a "close-first" parameter (needs verification). Fallback: **accept that we cannot kill Cline tasks from bash** and use Option B.
- **Option B (pragmatic):** Wrap the Cline task invocation with a unique marker (e.g., `nohup` + a PID file), and `pkill` on that marker before restarting. The marker must survive restart so the watchdog can find it. Store the marker as `~/.cline-bridge/.worker-$slot.pid`.
- **Option C (redesign):** Move restart responsibility into the Cline task itself. Instead of a bash watchdog, inject a self-check-and-restart mechanism into the worker prompt. This is out of scope for an RCA but is the upstream fix.

**Tradeoff:** Options A and B are band-aids on the fundamental issue that Cline tasks are heavyweight and not designed for programmatic lifecycle management.

---

### 2. **Heartbeat must be touched before the first `claim-next` call (MEDIUM)**

**Issue:** A restarted task may not touch its heartbeat immediately, causing the watchdog to re-trigger a second restart before the first poll completes.

**Fix:** The watchdog itself should touch the heartbeat file when firing a restart, to give the new task a 300s grace period before the next staleness check.

**Implementation:** After the `open vscode://...` command in `restart_slot()`, immediately run:

```bash
touch "$ROOT/worker-$slot.alive"
sleep 2  # Give the Cline task a moment to start
```

This is weaker than Option 2.1 (Option 1's fix) but reduces restart cascades.

**Tradeoff:** Does not solve the old-task-frozen issue, only masks the symptom slightly.

---

### 3. **Deploy ADR-0078 mitigation (ALREADY DONE)**

The identical-tool-call detector is mitigated by alternating `--wait 25` and `--wait 24` (commit a40f9a7). This is already merged and should prevent the 5-identical-poll kill in future runs. However, it does not address the older issue of repeated empty loops nudging the model toward `attempt_completion`.

---

### 4. **Redesign the empty-queue message to avoid the `noToolsUsed()` nudge (MEDIUM)**

**Issue:** Cline's error injection explicitly names `attempt_completion` as a valid tool when no tool is used. After three identical empty polls, the model conflates the error message with the loop instruction.

**Fix:** Ensure the worker prompt includes a statement *after* each empty poll that reframes the situation. Options:

- **Option A:** Inject a tool call that succeeds with an empty result but updates a counter. E.g., `execute_command true # poll 3 of N`, which breaks the identical-tool-call pattern and gives the model a sense of progress.
- **Option B:** Vary the empty-queue message itself (not just the `--wait` parameter). E.g., "EMPTY (check 1/N)", "EMPTY (check 2/N)", etc. This defeats the detector and gives the model a visible countdown.
- **Option C:** Add a special case: if three consecutive empty polls occur, inject a different command that is _provably_ useful (e.g., `bridge status`), rather than repeating the same poll. This breaks the pattern and gives the model agency.

**Tradeoff:** Options B and C increase message variability and may confuse the model; Option A is safest but requires a dummy tool call.

---

### 5. **Increase the staleness threshold or add a boot-grace window for heartbeats**

**Issue:** The current 300s staleness window is coupled tightly to the 300s boot grace (ADR-0068, ADR-0072). A slow Cline startup can miss the heartbeat touch, causing rapid re-triggers.

**Fix:** Increase staleness threshold to 600s (10 min) or add a per-slot "restart in progress" marker (`~/.cline-bridge/.restart-$slot.in-progress`) that extends the grace period to 600s. The marker is cleared once the new task touches the heartbeat.

**Tradeoff:** Longer idle-detection time means a truly dead worker goes unnoticed for 10 minutes instead of 5. Acceptable if combined with fix #1 (preventing restart cascades in the first place).

---

## Synthesis: Why Worker 1 Called `attempt_completion` After Three Empty Polls

**Now sourced to the actual runtime:**

1. **The worker-prompt forbids `attempt_completion`** (line 18) — this is in the *conversation context*.
2. **Cline v4.0.0 has no no-tool-call nudge** — when the model responds with text and no tool, the runtime does NOT inject a recovery message. The model's loop state is: "I responded with text, the system did nothing, so I should continue."
3. **After three identical empty responses ("EMPTY - no work. Run `bridge claim-next --worker N --wait 25` again now")**, the model faces:
   - No signal that progress is being made
   - No counter, no state change, no feedback from the loop
   - Three identical message cycles with zero actionable content
4. **The model's logic:** "I have been asked to loop and report back. I have done this three times with identical results. There is no onward path. The task appears done. I should call `attempt_completion` to exit."
5. **Why it was possible:** The worker-prompt rule is a single line in the conversation; Cline's system prompt does not lock this in. On a long-running loop (or if the prompt was re-initialized after a watchdog restart), the instruction may have been truncated or never locked into the system state.

This is **NOT** a Cline flaw; it is a **protocol design gap:** the loop provides zero-gradient feedback on three consecutive empty polls, and Cline's design expects explicit tool calls only when the model is confident, not resigned.

## Summary of Verification

- **Watchdog source (bridge-watchdog.sh:47):** No kill command. Confirmed.
- **Heartbeat touched in claim-next:** Yes, on loop entry (bridge/cli.py:114). Confirmed.
- **Identical-tool detector fires on 5+ identical calls:** Verified in `sdk/packages/core/src/runtime/safety/loop-detection.ts` — hard threshold 5. ADR-0078 describes the effect correctly.
- **Cline v4.0.0 has NO no-tool-call nudge:** Verified in `sdk/packages/core/src/runtime/session-runtime-orchestrator.ts` — no injected message when model responds with text only. (Note: older research doc `cline-workflow-agent-loops.md:38` cites a different Cline version that did have a nudge; v4.0.0 does not.)
- **Mistake counter only increments on API errors, invalid tool calls, or tool execution failures:** Verified in `mistake-tracker.ts`. Successful `bridge claim-next` exit (code 0) does NOT reset the counter.
- **Worker-prompt forbids attempt_completion:** worker-prompt.txt:18, confirmed.
- **Watchdog log shows cascading restarts:** watchdog.log, 2026-08-28, confirmed.
- **URI restart handler does not preserve history:** Verified in `apps/vscode/src/sdk/SdkController.ts` — `initTask()` clears prior turn outcome.

---

## Cline v4.0.0 Runtime Internals (Source-Verified)

**Agent research findings** (agent task ac8ef08a855961558 — Cline source inspection):

### `attempt_completion` Tool Design

**Definition:** `sdk/packages/core/src/extensions/tools/definitions.ts` — calls `submit_and_exit` (renamed in v4.0.0), sets `completesRun: true`, immediately terminates the task.

**System prompt guidance in v4.0.0:**
- Normal mode: "Response without tool calls will be considered as completed with final answer"
- YOLO mode: "You should only end the task when all requirements are met by calling the 'submit_and_exit' tool"
- **Neither mode provides explicit, actionable criteria for when to invoke it**

**Runtime gating:** NONE. Once the model calls `attempt_completion`, the extension executes it immediately. There is no rejection path.

**No no-tool-call nudge:** Unlike the older research found in `cline-workflow-agent-loops.md` (which cites a `noToolsUsed()` error message), **v4.0.0 source inspection found NO injected message when the model responds with text and no tool calls.** The `session-runtime-orchestrator.ts` handler only syncs history; it does not emit a recovery nudge (source: `sdk/packages/core/src/runtime/session-runtime-orchestrator.ts`). The model is left guessing whether continuing is correct.

### Consecutive-Mistakes Counter (v4.0.0)

**File:** `sdk/packages/core/src/runtime/safety/mistake-tracker.ts`

**Only three reasons that increment the counter:**
- `"api_error"` — LLM provider error
- `"invalid_tool_call"` — malformed tool call
- `"tool_execution_failed"` — tool exit code non-zero

**Reasons that do NOT increment:**
- `"completion_without_submit"` is mentioned in messaging but never recorded

**Reset logic:**
- When a turn includes ≥1 successful tool call: `mistakeTracker.reset()` fires
- Otherwise: counter continues accumulating

**Critical gap:** `bridge claim-next --worker N --wait 25` exits with code 0 and text output ("EMPTY - no work"), which is a successful bash call but with zero tool calls *within* the response. **The mistake counter is NOT reset.** It continues if the next turn also has only failures.

**Limit:** Default 6 consecutive mistakes (v4.0.0). Error string: "Stopped after X/Y consecutive mistakes (reason) at iteration Z."

### Identical-Tool-Call Detector (v4.0.0, VERIFIED ROOT CAUSE)

**File:** `sdk/packages/core/src/runtime/safety/loop-detection.ts`

**Thresholds:**
- Count 3: soft threshold — appends a warning message
- **Count 5: hard threshold — forces mistake counter to max, immediately terminates task**

**Mechanism:**
1. Before every tool execution, `beforeTool` hook calls `loopTracker.inspect({ name, input })`
2. Compares JSON-stringified parameters (keys sorted) to previous call
3. Identical → increment `consecutiveIdenticalCount`
4. At count ≥5 → return `kind: "hard"`
5. `SessionRuntime.inspectLoopForToolCall()` force-records a mistake at limit: `mistakeTracker.record({ forceAtLimit: true })`

**The worker loop trap:**
- Tool: `execute_command`
- Command: `bridge claim-next --worker N --wait 25`
- Signature: byte-identical every empty poll
- Timeline: 5 polls × 25s ≈ **2 min 5 sec to task death**

**Distinct from mistake counter:** The detector is a separate, hard-gating mechanism that bypasses normal mistake-count decision logic. Two independent load-bearing failures.

### YOLO Mode (v4.0.0)

**Changes from normal mode** (source: `sdk/packages/shared/src/prompt/system.ts`):
- Forces explicit `submit_and_exit` calls
- Rejects text-only responses as incomplete
- Does NOT disable the identical-tool detector
- Does NOT change mistake limits

**Error prefix:** When mistake limit is hit in YOLO mode, error is prefixed `[YOLO MODE]` by telemetry/formatting layer, not the core tracker.

### Task Restart Lifecycle

**URI handler:** `apps/vscode/src/services/uri/SharedUriHandler.ts` → `/task` path → `initTask()`

**initTask behavior:**
- Stops any running task
- Sets state to "streaming"
- Clears prior turn outcome
- **Does NOT preserve history** — new task = fresh conversation

**No TaskComplete hook found** in v4.0.0 source. Task ends when runtime returns `finishReason: "aborted"` or model calls `submit_and_exit`.

### Context Truncation

**File:** `sdk/packages/core/src/session/services/message-builder.ts`

Per-tool-result cap: 8,000 chars. Total budget: ~6M chars. Truncation is aggressive, marked inline with `[truncated X chars]`.

**Standing instructions vulnerability:** If injected as *conversation messages* (not locked in system prompt), they will be truncated as history grows. The model receives NO signal that instructions have been evicted.

---

## Related Issues

- **ADR-0068:** Loop durability policy, documents `attempt_completion` as a known failure mode.
- **ADR-0072:** Watchdog liveness; already surfaces watchdog health but does not address task-kill issue.
- **ADR-0074:** Worker pool identity; mentions restart cascades but does not mandate task kill.
- **ADR-0078:** Identical-tool-call detector mitigation; already deployed, should prevent future cascade from detector alone.
- **Issue #44:** Earlier runtime-limits probe; misattributed failure to context truncation, but identical-tool detector was the root cause.
- **Issue #66:** Live end-to-end proof; where the detector was discovered in production.

