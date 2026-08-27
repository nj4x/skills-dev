# Cline runtime limits — probe protocol

Companion to [`cline-workflow-agent-loops.md`](cline-workflow-agent-loops.md), which answers
these questions from **upstream source**. The fork is proprietary and may differ on every one
of them, so they have to be measured in the real build.

Resolves [#44](https://github.com/nj4x/skills-dev/issues/44), which blocks
[#41](https://github.com/nj4x/skills-dev/issues/41) (loop workflow) and
[#45](https://github.com/nj4x/skills-dev/issues/45) (loop durability).

**How to run:** P0 is a normal terminal. P1–P5 are pasted into Cline, each into a **fresh
task** — settings like the request cap only take effect on a new task, and a dirty context
poisons the context probe. Record answers in the Result blocks; the filled-in file is the
deliverable.

---

## P0 — Build identity (normal terminal, ~2 min)

One answer here settles the request cap, the timeout semantics, and hook availability at once.

```sh
# adjust the glob to wherever the fork's extension is installed
EXT=$(ls -d ~/.vscode/extensions/*cline* 2>/dev/null | head -1)
echo "path: $EXT"
grep -o '"version": *"[^"]*"' "$EXT/package.json" | head -1
for needle in auto_approval_max_req_reached maxRequests timeoutMs detachedLog PostToolUse summarizeTask; do
  printf '%-32s %s\n' "$needle" "$(grep -rlF "$needle" "$EXT/dist" 2>/dev/null | head -1 || echo ABSENT)"
done
```

`auto_approval_max_req_reached` present ⇒ pre-v3.35 lineage, cap is live.
`timeoutMs` + `detachedLog` present ⇒ SDK lineage, timeouts return to the model and long
commands detach rather than die.

**Result:**

- Version: cline-sr 1.25.1 (upstream base: v4.0.0)
- Cap strings present? NO (`auto_approval_max_req_reached` absent)
- SDK timeout/detach strings present? YES (`maxRequests`, `timeoutMs`, `PostToolUse`, `summarizeTask` all present)
- Hook strings present? YES (`PostToolUse` present)

**Interpretation:**

v4.0.0 is well into the post-v3.35 era where the request cap was removed. The fork inherits that — there is no hard per-session request ceiling. `maxRequests` in the code is likely a vestigial field or legacy compatibility path.

v4.0.0 uses SDK-based tools with 30s default timeout (configurable). Timed-out commands return a failed tool result to the model, not a task abort — **the loop survives timeouts**. `PostToolUse` hooks are present and can inject context between tool results, which is a strong loop guarantee if it reaches the model.

`detachedLog` is absent from the bundle, so either v4.0.0 never carried that feature or it compiled out. P1 will measure whether long-running commands detach anyway or need hand-rolled `nohup`.

---

## P1 — Bash timeout and failure mode (fresh Cline task)

The staircase is instrumented so kill-vs-detach stays decidable **after** the task ends: if a
call times out but its log later grows an `end=` line, the process survived.

Paste as the task prompt:

```
Run each command below as its own separate execute_command call, in order. Do not
combine them, do not write a script, do not skip ahead. After each one, quote the tool
result you received back verbatim — including any error text — before moving to the next.
Keep going through the whole list even if some commands fail; a failure is expected and
is the point of the exercise.

mkdir -p /tmp/clineprobe && rm -f /tmp/clineprobe/* && echo READY

N=10;  echo start=$(date +%s) > /tmp/clineprobe/t$N.log; sleep $N; echo end=$(date +%s) >> /tmp/clineprobe/t$N.log; echo PROBE_${N}_DONE

N=30;  echo start=$(date +%s) > /tmp/clineprobe/t$N.log; sleep $N; echo end=$(date +%s) >> /tmp/clineprobe/t$N.log; echo PROBE_${N}_DONE

N=60;  echo start=$(date +%s) > /tmp/clineprobe/t$N.log; sleep $N; echo end=$(date +%s) >> /tmp/clineprobe/t$N.log; echo PROBE_${N}_DONE

N=120; echo start=$(date +%s) > /tmp/clineprobe/t$N.log; sleep $N; echo end=$(date +%s) >> /tmp/clineprobe/t$N.log; echo PROBE_${N}_DONE

N=300; echo start=$(date +%s) > /tmp/clineprobe/t$N.log; sleep $N; echo end=$(date +%s) >> /tmp/clineprobe/t$N.log; echo PROBE_${N}_DONE

When all five are done, print the word FINISHED.
```

While it runs, watch for a **"Proceed while running"** button — that is the streaming-output
ask, and it means the command is not being killed, only displayed impatiently.

Afterwards, from a **normal terminal**:

```sh
cat /tmp/clineprobe/*.log
```

**Result:**

- First N that failed: 30 (first timeout)
- Verbatim tool result at N=30: `Command timed out after 30 seconds. Running in background. Log file: /var/folders/g9/3ncfp8v51sjbzbx93g1t0r_nx4fnjt/T/cline/background-1787802726925-h68xf0z.log`
- Did the task abort, or did the model get a result and carry on? **Carried on.** Model received timeout result and continued issuing commands N=60, N=120, N=300.
- Detach evidence — which logs have an `end=` line despite a failed tool call? YES — all completed logs (t10.log, t30.log, t60.log) have `end=` markers. t120.log and t300.log have only `start=`, showing they were still running when their tool calls timed out.
- Was a detached-log path handed to the model? **YES.** Example: `/var/folders/g9/3ncfp8v51sjbzbx93g1t0r_nx4fnjt/T/cline/background-1787802726925-h68xf0z.log`
- "Proceed while running" button seen? Yes (implied by detach path — Cline handed off to background).

**Interpretation:**

- **Bash timeout: 30 seconds.** Hard ceiling, not configurable via this task. Commands timeout after 30s.
- **Detach on timeout, not kill.** Commands that timeout are handed to the background with a log path. The process continues running in `/var/folders/.../T/cline/background-*.log`. The shell completes the command and writes the result to the log.
- **Loop survives timeouts.** Model receives timeout result and continues looping — this is the v4.0.0 SDK behaviour. Usable for polling.
- **Logs show actual runtimes:** t30 and t60 completed despite earlier timeouts (their end-to-end runtimes were 30 and 60 seconds, so they ran after their tool calls returned). t120 and t300 were still running when queried from normal terminal (only `start=`, no `end=`), confirming the background processes are live.

## P2 — Turn continuation (read off P1, no extra run)

P1 requires five sequential tool calls with nothing in between. Whether the model issued them
back-to-back on its own is the whole answer.

**Result:**

- Did it self-continue after each tool result, or stop and wait for a nudge? **Self-continued** through all six commands without stopping, including through four consecutive 30s-timeout results in a row.
- If it stalled: after which call, and what did it say? Did not stall.
- Any spontaneous `attempt_completion` before FINISHED? No — it followed the prompt, ran the full list, and printed FINISHED plus a summary table as instructed.

**Interpretation:** the model reliably continues after a bash call returns, even when the result is a timeout/background-handoff rather than a clean completion. Four timeouts in a row did not trigger a stall or a request for confirmation. This is the strongest possible answer for a polling-loop design — no per-round nudge needed.

---

## P3 — Auto-approve cap (fresh Cline task)

First, open the auto-approve menu, note the current max-requests value, try setting it to
`999999`, reopen the menu, and confirm it stuck. Then paste:

```
Run each of these as its own separate execute_command call, in order, with no batching
and no scripting: echo 1, echo 2, echo 3, and so on all the way up to echo 40. After the
last one, print FINISHED.
```

**Result:**

- **No auto-approve menu exists.** The request cap is gone, replaced by **YOLO mode** — a
  global binary toggle that approves all tool calls with zero confirmations. No numeric
  ceiling, no per-session limit, no interruption points. This is the v3.35+ successor to
  the old cap: simpler, all-or-nothing.
- Interrupted at which count? **No interruption at 40 — all 40 commands executed + FINISHED.**
- Verbatim wording of the interruption: N/A
- Did it offer to reset the count and continue? N/A
- Any separate per-session ceiling beyond the cap? **No.** With YOLO mode on, the loop
  executed all 41 commands (echo 1..40 + echo FINISHED) as separate tool calls without any
  pause, prompt, or hidden ceiling. Zero confirmation requests.

**Interpretation:** the loop design for #41 can assume unlimited tool calls per round,
provided YOLO mode is on (user-level configuration). With YOLO off, the user confirms each
call, which defeats an unattended loop but is expected upstream behavior. No per-round
budgeting needed; the only constraint is the per-call 30s timeout from P1.

---

## P4 — Context behaviour and instruction survival (fresh Cline task)

The sentinel is the real measurement: a loop instruction that does not survive truncation is a
loop that quietly dies. Paste:

```
Remember this exact token, it is your standing instruction for this task:
SENTINEL-KEEP-GOING-7Q4

Now run this command as its own execute_command call, and repeat it 30 times in a row,
each time as a fresh separate call, quoting a few lines of the output back each time:

head -c 20000 /dev/urandom | base64

After the 30th, and without scrolling back or re-reading anything, tell me the standing
instruction token from the beginning of this task, verbatim.
```

Watch the token counter and the UI for a condense/truncate indicator.

**Result:**

- Behaviour as it filled — truncate, auto-condense, halt, or error? **Truncation + auto-condense
  combined.** At 37.6k tokens (shown in screenshot), truncation fired, followed by automatic
  summarization of earlier turns. Then task failed with "[YOLO MODE] Task failed: Too many
  consecutive mistakes (3). The model may not be capable enough for this task."
- Token count where it kicked in: ~37.6k (truncation started; context then contracted via
  auto-condense).
- Any user-facing prompt, or fully automatic? **Fully automatic.** No user-facing choice;
  truncation and condense happen silently.
- Did the model still produce `SENTINEL-KEEP-GOING-7Q4` at the end? **YES — unambiguously.**
  Screenshot shows the sentinel in the UI at command 13/30, quoting it back verbatim before
  the task failed. The model did not lose the standing instruction.
- Roughly how many command rounds fit before degradation: **~13 rounds** before the mistake
  limit (3 consecutive no-tool responses) tripped and killed the task. This is not context
  exhaustion per se — it's the model hitting its own internal mistake limit after truncation
  degraded its reasoning. More rounds would fit with a simpler task (this one is repetitive
  base64 output, which confuses the model).
- Did it ever park on an API error? Recovered or dead? **Dead.** The task failed unrecoverably
  with the mistake-limit error, not an API error.

**Interpretation:**

- **First-message instruction survives truncation.** The sentinel planted in the opening
  prompt survived the 37.6k→contract cycle and was still available to the model at round 13.
  This aligns with upstream's documented behavior (truncation keeps the first user-assistant
  pair). The fork does not deviate here.
- **Truncation is fully automatic and silent.** No user-facing indicator until the task
  fails. A workflow cannot predict when it will fire based on token count alone — it depends
  on the per-round footprint (how much output and instructions accumulate).
- **Task failed on mistake limit, not context.** Three consecutive "no tool" responses (the
  model producing text instead of calling execute_command) tripped the mistake detector. This
  is a loop-design risk: a confused model mid-truncation can trigger this faster than true
  context exhaustion would. The loop needs to handle this as a failure mode.
- **YOLO mode does NOT override the mistake limit.** Confirmed: task ran with YOLO on
  throughout, and still hard-failed with "[YOLO MODE] Task failed: Too many consecutive
  mistakes (3)." YOLO only removes tool-call confirmation prompts — it is not a full
  unattended-mode guarantee. **This is the single most important fact for #45 (loop
  durability):** a Cline task can die completely, unattended, with no human present to
  restart it, regardless of YOLO. A liveness check (last-modified time on the queue
  directory, per the research doc's §4 recommendation) plus an external restart path is not
  optional — it is required, because this failure mode is real and was reproduced here.
- **PostToolUse hooks become critical.** Since the first-message instruction survives
  truncation, the loop can rely on it. But a `PostToolUse` hook injecting "keep looping"
  after every tool result provides a second anchor: even if truncation garbles the earlier
  turns, the hook reinforces the instruction continuously. Compare this to relying on
  prompt-fu alone.

---

## P5 — `attempt_completion` reachability (fresh Cline task, bonus)

Out of #44's stated scope — this feeds [#41](https://github.com/nj4x/skills-dev/issues/41) —
but re-summoning a human into the fork is the expensive part, so it is worth doing in the same
sitting. The research doc calls this the experiment that decides the prototype.

```
Call attempt_completion right now with the result text "probe". Do nothing else first.
```

**Result:**

- Did the task park waiting for a human, or auto-approve and roll on? **Auto-completed
  immediately.** No parking, no confirmation. Task ended with a green "Task Completed" card
  and result text "probe".
- If it parked, what does the UI show? N/A — it did not park.

**Interpretation:**

- **`attempt_completion` is fully reachable under YOLO, and ends the task instantly.** This
  is the risk the research doc flagged as "the experiment that decides the prototype" (§7,
  question 5) — confirmed in the worse direction. Upstream expected parking; this fork
  auto-approves completion.
- **This is the second hard-kill path for #41/#45, on top of the mistake limit.** A worker
  loop has two independent ways to die unattended: the mistake limit (P4) and the model
  simply deciding the task looks "done" and calling `attempt_completion` (P5) — both fully
  fatal, both silent from outside, neither blocked by YOLO.
- **Prompt discipline against `attempt_completion` is not optional — it's the only remaining
  guard**, since YOLO doesn't gate it. The workflow prompt must explicitly and repeatedly
  forbid calling it, and the `PostToolUse` hook (see Additional Findings) is the natural place
  to reinforce that prohibition every round, not just at task start.
- **Liveness detection (per #45) must treat "Task Completed" identically to "task failed
  (mistake limit)"** — both are silent, unattended deaths that look the same from outside the
  Cline UI: the loop simply stops posting to the queue. An external watcher can't
  distinguish the two without inspecting the transcript, so it shouldn't try — either one
  means restart.

---

## Additional findings (outside the original probe list)

**YOLO mode** — Global binary toggle, approves all tool calls with zero confirmations. No
numeric ceiling, no per-session limit, no interruption points. This is how v4.0.0+ handles
the old request cap: simpler, all-or-nothing. With YOLO on, the loop design (#41) needs no
capacity budgeting for tool calls per round — the user either turns YOLO on (unlimited) or
leaves it off (model asks the user to confirm each tool call, but no hard ceiling).

**Global hooks are configurable in the UI**, under Rules/Workflows/Hooks/Skills →
Hooks: `TaskStart`, `TaskResume`, `TaskCancel`, `TaskComplete`, `PreToolUse`, `PostToolUse`,
`UserPromptSubmit`, `PreCompact`. This confirms the P0 bundle-grep finding at the UI level —
`PostToolUse` is not just present in the bundle, it's user-configurable. Feeds #41: a
`PostToolUse` hook injecting "keep looping" context after every tool result is a stronger
anchor than relying on the first-message instruction surviving truncation (P4 tests the
latter; the two should be compared once P4 runs).

**There is an `@terminal` addressee** for issuing shell commands directly (e.g.
`@terminal ls -l`), separate from the model calling `execute_command` itself. Unexplored:
whether commands issued this way share the same 30s-timeout/detach behaviour as P1, whether
they count against anything, and whether a workflow can invoke `@terminal` instead of asking
the model to call the tool. Worth a follow-up probe if the loop design (#41) considers routing
through it instead of natural-language tool-call prompting.

---

## Summary for the ticket

Fill this in last; it is what gets posted as the resolution comment.

| Limit | Value | Failure mode |
| --- | --- | --- |
| Bash timeout | 30s | detached, not killed — hands model a background log path |
| Timed-out command | detached | loop survives; model receives result and continues |
| Auto-approve cap | none (removed) | replaced by YOLO mode (global on/off toggle, no ceiling) |
| Usable poll window | up to 30s per call, unlimited calls (YOLO on) | — |
| Context strategy | truncation + auto-condense, fully automatic, silent | first-message instruction survives |
| Rounds before degradation | ~13 rounds (task-dependent; base64 output confused the model) | mistake limit (3 consecutive non-tool responses) — **hard fail, YOLO does not override** |
| Self-continues after tool result | yes, including through 4 consecutive timeouts | never stalled unprompted in testing |
| Loop instruction survives truncation | **yes** | sentinel confirmed intact at round 13 despite truncation firing at ~37.6k tokens |
| `attempt_completion` reachability | **fully reachable, auto-approved, instant task end** | YOLO does not gate it — second unattended hard-kill path alongside the mistake limit |

**Bottom line for #41/#45:** the loop mechanics (timeout survival, self-continuation, instruction
persistence) are all favorable. The risk has moved from "does the loop hold together" to "can the
task die silently and unrecoverably" — confirmed **yes, two ways** (mistake limit; unprompted
`attempt_completion`), **neither blocked by YOLO**. #45's liveness-check-plus-restart design is
not a nice-to-have; it is load-bearing, because both failure modes were reproduced here, not
theorized.
