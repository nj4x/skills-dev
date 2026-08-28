---
artifact-type: adr
lineage-rules: exempt
---

# ADR-0071: Cline Bridge Worker Loop Workflow

> Lineage exempt: this repository is the skills-dev tooling workspace itself and carries no
> `.data/requirements/` FS/SRS corpus. This ADR records a decision about the workspace's own
> internal tooling, not a product capability traceable to a requirement.

**Status**: Approved

**Context**

The Cline-side worker must loop over the filesystem queue designed in ADR-0069, under the durability constraints of ADR-0068 and the MCP interface specified in ADR-0070. Issue #44's runtime probe confirmed two unattended, unblockable ways the worker dies: the 3-consecutive-mistake limit and spontaneous `attempt_completion` — neither is gated by YOLO mode. The probe also confirmed that the first-message instruction survives context truncation and that continuation through tool results is automatic. This ticket specifies the exact workflow prompt that keeps the model looping without reaching for a human.

**Decision**

## Canonical prompt file

The worker prompt lives at `~/.cline-bridge/worker-prompt.txt` (the runtime path) and is source-controlled at `mcp/cline-bridge/worker-prompt.txt` in the repo. The watchdog (ADR-0068 point 3) reads this file on every restart and passes its contents as the first user message to a fresh Cline task — unchanged, never regenerated inline.

An installation/initialization step copies the repo version to `~/.cline-bridge/worker-prompt.txt` once.

## Absolute rules against unattended death

The probe confirmed that YOLO mode does not gate the mistake limit or `attempt_completion`. The prompt embeds three absolute rules as literal prohibitions:

1. **Never call `attempt_completion`.** This ends the task instantly with no recovery path. The consequence of this call is stated plainly to keep the model from reasoning "I've done good work, time to complete."
2. **Never call `ask_followup_question` or `condense`.** Both are permanent parks with no human to dismiss them.
3. **Every loop turn must include at least one tool call.** This guards against the mistake limit (3 consecutive text-only responses). If the model needs to explain something or wait, it must do so inside a tool result, not as bare prose.

These three sentences are not framed as preferences or goals — they are absolute rules, stated as commands. Rule 3 is the most concrete: "never respond with text alone" gives the model an unambiguous, testable constraint on every turn.

## The work loop

The prompt prescribes a single loop sequence:

1. Call `bridge claim-next --wait 25` (blocks server-side; see §**CLI amendment** below)
2. If empty, go back to step 1 immediately — no sleep in between (amended; see §**No pacing sleep between empty polls**)
3. On work received: run `execute_command` as needed to answer
4. Write answer with `write_to_file /tmp/bridge-answer.txt` (avoids shell quoting hazards; see §**Answer transfer** below)
5. Call `bridge answer <id> --file /tmp/bridge-answer.txt`
6. Return to step 1

This sequence nests a "never call these tools" constraint with a "always call at least one tool per turn" constraint. The model satisfies both by following the loop: every turn has at least one tool call (`claim-next`, `execute_command`, `write_to_file`, or `answer`).

## No pacing sleep between empty polls

The original step 2 told the worker to `sleep 5` before retrying. Real usage showed the model
collapses the instruction into a single chained command, `sleep 5 && bridge claim-next --wait 25`,
whose combined duration lands at ~30s — exactly Cline's default `execute_command` timeout — so the
call is killed and its output diverted to a background log. The worker then loses the turn.

The sleep bought nothing: `claim-next --wait N` already blocks server-side and polls the queue at
`POLL_INTERVAL` (0.5s), so the filesystem lock is paced from inside the CLI, not by the caller. Step 2
now retries immediately, and both the prompt and the CLI's `EMPTY_MESSAGE` say explicitly not to
prefix the retry with a sleep — the message is what the model sees on every empty poll, so it is the
instruction that must survive context truncation.

The 25s wait stays comfortably inside the 30s ceiling. A wider window would need the optional
`timeout` parameter `execute_command` accepts under YOLO, which is a separate change.

## What the model does not see

The prompt is explicit about the model's scope and blindness:
- Bash only; no repo access
- Questions are complete and self-contained
- No visibility into the peer model
- Claims are permanent (no re-delivery, no retries)

This sets ground truth for any reasoning about what a question means or whether to retry it.

## Loop-until-stopped termination

The prompt states: "When a human stops this Cline task, your work is done." There is no sentinel condition that allows the model to call `attempt_completion` on its own. Only a human stopping the task ends the work. This eliminates a class of conditional-exception bugs where the model reasons "I should stop when X" and risks getting it wrong.

The watchdog (ADR-0068) ensures that if the task dies before a human stops it, a fresh one restarts with the same prompt, carrying the loop forward.

## CLI amendments

Two CLI verbs gain or change signatures as a consequence of this workflow:

- **`claim-next` gains `--wait N`** (previously implicitly immediate): blocks the server-side lock-and-scan loop for up to N seconds, returning the oldest pending record immediately if one arrives, or an empty result if N seconds elapse with no work. Timeout is specified to sit comfortably inside the measured 30s bash timeout (ADR-0068 references; chosen at 25s to leave margin). This makes a single LLM turn cover up to 25 seconds of waiting without spinning on the queue — critical to keeping context growth manageable when the queue is idle.
- **`answer` gains `--file` option** (in addition to or instead of inline `<text>` argument): reads the answer body from a file instead of parsing it from the command line. This avoids shell quoting hazards and keeps the answer text entirely outside any shell's parsing. The model calls `write_to_file /tmp/bridge-answer.txt` before invoking `bridge answer <id> --file /tmp/bridge-answer.txt`.

## Rule vs. workflow placement

The absolute prohibitions are stated in this prompt (the first user message) but *should also appear in a `.clinerules/` file* for a Cline instance dedicated to this bridge, because:

- Rules are appended to the system prompt on every request, competing on more even footing with Cline's built-in push toward `attempt_completion`
- The first-message instruction survives truncation (confirmed by the probe), but a rule survives on every single turn, regardless of truncation
- Duplication is intentional belt-and-braces on the single failure mode whose prohibition kills the design

The `.clinerules/` file is the responsibility of the bridge-setup workflow; this ADR specifies only the canonical first-message prompt.

## Consequences

- The watchdog (ADR-0068) restarts with this exact prompt every time. Changes to the prompt require: (1) update the repo copy at `mcp/cline-bridge/worker-prompt.txt`; (2) re-run the installation step that copies it to `~/.cline-bridge/worker-prompt.txt`; (3) restart the Cline task manually (the watchdog doesn't re-read a stale file mid-task).
- The `--wait` addition to `claim-next` means a single poll can cover 25 seconds without consuming an LLM turn for inference — trading bash timeout for context savings. A poll returns immediately with an empty result if no work arrives, so the model doesn't block the watchdog's liveness-check window (ADR-0068 point 2: heartbeat on every poll).
- Writing the answer to a file is one extra tool call per round, but eliminates a class of shell-injection hazards on the answer side. The question is still trusted by the design — trust-boundary decisions belong to #46.
- No `PostToolUse` hook is required by this design (though one could reinforce the prohibitions if added later). The prompt's first-message instruction and a `.clinerules/` rule are sufficient to establish the constraints.
