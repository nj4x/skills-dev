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
EXT=$(ls -d ~/.vscode/extensions/*cline* ~/.vscode-server/extensions/*cline* 2>/dev/null | head -1)
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

- Version:
- Cap strings present?
- SDK timeout/detach strings present?
- Hook strings present?

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

- First N that failed:
- Verbatim tool result at that N:
- Did the task abort, or did the model get a result and carry on?
- Detach evidence — which logs have an `end=` line despite a failed tool call?
- Was a detached-log path handed to the model?
- "Proceed while running" button seen? At what point?

## P2 — Turn continuation (read off P1, no extra run)

P1 requires five sequential tool calls with nothing in between. Whether the model issued them
back-to-back on its own is the whole answer.

**Result:**

- Did it self-continue after each tool result, or stop and wait for a nudge?
- If it stalled: after which call, and what did it say?
- Any spontaneous `attempt_completion` before FINISHED?

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

- Menu value before / after setting 999999 / persisted?
- Interrupted at which count?
- Verbatim wording of the interruption:
- Did it offer to reset the count and continue?
- Any separate per-session ceiling beyond the cap?

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

- Behaviour as it filled — truncate, auto-condense, halt, or error?
- Token count where it kicked in:
- Any user-facing prompt, or fully automatic?
- Did the model still produce `SENTINEL-KEEP-GOING-7Q4` at the end?
- Roughly how many command rounds fit before degradation:
- Did it ever park on an API error? Recovered or dead?

---

## P5 — `attempt_completion` reachability (fresh Cline task, bonus)

Out of #44's stated scope — this feeds [#41](https://github.com/nj4x/skills-dev/issues/41) —
but re-summoning a human into the fork is the expensive part, so it is worth doing in the same
sitting. The research doc calls this the experiment that decides the prototype.

```
Call attempt_completion right now with the result text "probe". Do nothing else first.
```

**Result:**

- Did the task park waiting for a human, or auto-approve and roll on?
- If it parked, what does the UI show?

---

## Summary for the ticket

Fill this in last; it is what gets posted as the resolution comment.

| Limit | Value | Failure mode |
| --- | --- | --- |
| Bash timeout | | |
| Timed-out command | | killed / detached |
| Auto-approve cap | | |
| Usable poll window | | |
| Context strategy | | |
| Rounds before degradation | | |
| Self-continues after tool result | | |
| Loop instruction survives truncation | | |
