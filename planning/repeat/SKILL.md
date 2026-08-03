---
name: repeat
description: Reusable generate→review→refine loop engine; consumed by other skills (e.g. critic) and directly invocable over any artifact.
disable-model-invocation: true
arguments: [mode, max_iterations]
---

# The repeat loop contract

This skill defines a **reusable, artifact-agnostic generate→review→refine loop**. It is consumed by other skills (e.g., `critic`) which bind the named extension points to their specific artifact and reviewer logic. It can also be invoked directly to drive a generic review loop over any active artifact.

---

## Guards

- If MAX_ITERATIONS is not a positive integer (empty, non-numeric, zero, or negative), set it to `∞` (loop until approved). A hard backstop of 10 applies silently in this case — if the backstop is reached without approval, emit a warning banner and go to Finalize.
- If MAX_ITERATIONS is an explicit positive integer, treat it as a hard cap regardless of approval status.
- Each iteration spawns up to 2 Agent sub-agents (generator + reviewer).
- MODE defaults to `guided` if empty, missing, or not the literal `auto`. Passing `auto` explicitly opts into fully unattended operation.

---

## Mode detection

Run immediately after guard checks:

- **FRESH** — a task/prompt is provided (non-empty, not an unsubstituted placeholder). The generator creates the artifact from scratch.
- **PICKUP** — no task arg or placeholder only. Locate the active artifact via this resolution order:
  1. **Explicit artifact path** — if the caller bound one (a path passed by the invoker, e.g. critic's `pickup:<path>` sentinel), read the artifact directly from that path. This is the **plan-mode-independent** path: it is the only resolution that works in environments where plan mode is disabled (agent / headless runs, where the `EnterPlanMode`/`ExitPlanMode` tools do not exist and no plan-mode context line is ever emitted). Callers running outside interactive plan mode MUST bind an explicit path.
  2. **Plan-mode context line** `A plan file exists from plan mode at: <path>` — used only when plan mode is available and active (interactive Claude Code).
  3. **MARK-REPLAY detection** (below).
  4. Hard-stop: `No active artifact found. Pass an explicit artifact path, provide a task argument, or activate a plan in plan mode first.`

### MARK-REPLAY detection (PICKUP only — runs before the hard stop)

If neither an explicit artifact path nor a plan-mode artifact is found:

1. `id = echo $CLAUDE_CODE_SESSION_ID`. If empty → continue to the hard stop.
2. If `~/.claude/marks/<id>.md` does not exist → continue to the hard stop.
3. Read the mark file (Read tool). Parse `transcript`, `anchor_line` (call it `N`), and `note`.
4. Recover the dialog span with a transcript extractor. Invoke it via Bash → `python3`, passing **only** the file path and `N` as argv — never artifact text as a shell argument (honours the no-artifact-in-shell-args invariant). The extractor:
   - reads `<transcript>`, tracking a 1-based line index, and takes records with line-index `> N`;
   - wraps each `json.loads` in try/except, skipping (and counting) lines that fail to parse, so a partial final write does not abort recovery;
   - keeps records whose `type` is `user` or `assistant` and whose `message.content` has text; flattens content blocks to text; skips `tool_use` / `tool_result` blocks and meta records;
   - drops a leading `/mark`-confirmation turn if present at the start of the span;
   - drops **exactly one** trailing `user` turn — the `/repeat` invocation itself, identified by its content (not by removing a contiguous run of user turns), so a genuine user dialog turn immediately before `/repeat` is preserved;
   - prints a compact `role: text` digest of the remaining turns (truncate each turn to ~4000 chars to bound size).
5. If the digest is empty (nothing happened after the mark) → continue to the hard stop with: `Mark found but no dialog after the anchor. Continue the conversation, then /repeat.`
6. Otherwise set:
   - `task = "Synthesize and carry out the intent of this marked dialog.\n\n"` + (if `note != "none"`: `"FOCUS: <note>\n\n"`) + `"DIALOG SPAN:\n<digest>"`
   - `MODE = FRESH`
   - print: `  Mark replay: <transcript>  (lines after <N>)`
   - print: `  Focus: <note or "(none)">`
   - continue to the repeat loop (do **not** hard stop).

Because `MODE` is set to `FRESH` **before** the loop begins, the rest of the contract is unchanged: GENERATE_STEP runs at iteration 0 to synthesize the artifact from `task`, and the standard FRESH FINALIZE path applies. `task` is a local variable injected here, exactly as PICKUP loads `artifact_text` locally — the `arguments` frontmatter is not involved.

**Reference extractor** (`python3 extract.py "$TRANSCRIPT" "$N"`-style; path + N as argv only):

- Read lines; track a 1-based index; `try/except` each `json.loads`, skipping malformed lines.
- For index `> N`, select records with `type == "user"` or `type == "assistant"` that have text in `message.content`; flatten content blocks to text; skip `tool_use` / `tool_result` blocks.
- Collect into an ordered list. Drop a leading `/mark`-confirmation turn if present. Pop **exactly one** trailing `user` turn — the `/repeat` trigger, matched by content — leaving a real preceding user turn intact.
- Print `role: text` lines, each truncated to ~4000 chars.

---

## Decision Protocol

The generator applies this protocol before baking any assumption into the artifact.

**Classification:**

| Type | Examples | Behavior |
|------|---------|----------|
| **Safe-default** | File naming, step ordering, log levels, comment style | Decide and continue in both modes |
| **Assumption-bearing** | Architecture choices; metadata/schema field names or semantics; external-integration patterns (API contracts, auth flows, message formats, third-party SDKs); any decision that cannot be verified from available context | Mode-dependent (see below) |

**Default (`guided`) mode:**

- The generator sub-agent does NOT ask the user directly. Instead it returns a `flagged_decisions` list alongside the artifact text (as a JSON block appended after the artifact, on its own line: `FLAGGED_DECISIONS: [{"decision": "...", "why_flagged": "..."}]`).
- The **orchestrator** (this skill, not the sub-agent) reads that list and calls `AskUserQuestion` for each flagged decision.
- Answers are stored as `user_answers` and fed into the next GENERATE_STEP prompt.
- Safe-default decisions are never flagged.

**`auto` mode (opt-in, fully unattended):**

- Pick the documented safe default for assumption-bearing decisions.
- Record each decision in an **"Assumptions made"** section appended to the artifact.
- Never pause.

---

## Extension points

Callers bind these three steps. Each is invoked at the point shown in the loop below.

```
GENERATE_STEP(iteration, task, prev_issues, prev_fixes, mode, user_answers?)
  → { artifact_text: string, flagged_decisions?: {decision, why_flagged}[] }

REVIEW_STEP(artifact_text)
  → { verdict: "approve"|"revise", severity: "none"|"minor"|"major",
      issues: string[], fixes: string[] }

FINALIZE_STEP(artifact_text, auto_approval, ledger, verdict, severity, issues, max_iterations)
  → void   (writes output, handles any mode transitions, emits markers)
```

When invoked directly (not as a contract consumed by another skill), the caller is the user and the generator/reviewer defaults are a general-purpose planner and adversarial critic. In that case follow the `critic` skill's extension point bindings as a reference implementation.

---

## The repeat loop

Initialize: `iteration = 0`, `artifact_text = ""`, `verdict = ""`, `severity = ""`, `issues = []`, `fixes = []`, `ledger = []`, `user_answers = []`.

### Audio-cue suppression (LOOP START)

At loop start — before the first iteration — suppress per-turn Stop chatter by calling `say_skill_start` from the shared helper:

```sh
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_start || true
```

This creates a per-session marker that `~/.claude/hooks/say-cue.sh` checks in the `stop` event handler: while it exists, per-turn Stop cues are suppressed. The single completion cue is emitted from FINALIZE_STEP via `say_skill_done`. The marker MUST be removed on every exit path (see Finalization contract and Hard invariants).

In PICKUP mode, `artifact_text` is already loaded from the active artifact.

### Each iteration

**1. GENERATE_STEP**

- If `iteration == 0` and PICKUP: skip; `artifact_text` is already loaded.
- Otherwise: invoke GENERATE_STEP with `(iteration, task, issues, fixes, mode, user_answers)`.

Hard abort if the call fails or `artifact_text` (after stripping any FLAGGED_DECISIONS block) is empty.

**In `guided` mode (default)** (FRESH only, after GENERATE_STEP returns):

If `flagged_decisions` is non-empty:
1. Call `AskUserQuestion` for each flagged decision (one question per decision; include the `why_flagged` reason as context).
2. Collect answers into `user_answers`.
3. Re-invoke GENERATE_STEP with `user_answers` to incorporate the answers before the review.

**2. REVIEW_STEP**

Invoke REVIEW_STEP with `artifact_text`. Hard abort on failure or unparseable response — never treat as approval or revise.

Append `{ iteration: iteration+1, verdict, severity }` to `ledger`.

Print: `  reviewer #<iteration+1>   <verdict> (<severity>)`

**3. STOP_CONDITIONS** (evaluate in order after each REVIEW_STEP):

1. `verdict == "approve"` → go to Finalize
2. If the caller sets `halt_convergence_guard == true` → go to Finalize and emit: `Convergence guard halted: major count did not decrease. Standing issues:` followed by all open major issues.
3. `MAX_ITERATIONS != ∞ AND iteration + 1 >= MAX_ITERATIONS` → go to Finalize (explicit cap reached)
4. `MAX_ITERATIONS == ∞ AND iteration + 1 >= 10` → go to Finalize (backstop reached)
5. Otherwise: increment `iteration`, go back to step 1

**4. Finalize**

Compute:
```
cap_reached = (MAX_ITERATIONS != ∞ AND iteration + 1 >= MAX_ITERATIONS) OR (MAX_ITERATIONS == ∞ AND iteration + 1 >= 10)
auto_approval = (verdict == "approve" AND severity != "major" AND NOT cap_reached)
```

Invoke FINALIZE_STEP with all collected state. Return.

---

## Finalization contract

FINALIZE_STEP must produce at minimum:

**Single completion cue (audio):** Emit exactly one spoken completion cue for the whole loop, then clear the suppression marker, using the shared helper. The `/repeat` completion cue is intentionally unconditional and separate from the general Stop opt-in (R4); it always fires (subject only to a global master disable, if implemented later):

```sh
proj="$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")"
proj_say="$(printf '%s' "$proj" | tr '_-' '  ')"
msg="Repeat loop finished${proj_say:+ in ${proj_say}}."
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_done "$msg" || true
```

**Exhaustion banner** (only when cap reached without approval):
```
⚠ Reached iteration limit (<N>) without reviewer approval. Presenting the best available artifact; unresolved issues are listed below.
```
When the backstop fired (MAX_ITERATIONS was unspecified), prefix the banner with: `⚠ No iteration limit was set — stopping at the safety backstop (10).`

**Session ledger** — tabular, one row per iteration plus an orchestrator row.

**Review summary** — final verdict, severity, iterations used, approval status (`auto_approval`), remaining issues.

Callers extend FINALIZE_STEP with artifact-type-specific output (file writes, plan-mode transitions, downstream marker lines, etc.). Any plan-mode transition a caller adds (e.g. `EnterPlanMode`/`ExitPlanMode`) is **optional and must degrade gracefully**: when those tools are unavailable (plan mode disabled — agent / headless runs), the caller writes the artifact to its resolved file path and presents it as text instead. FINALIZE must never hard-abort merely because plan-mode tools are absent.

---

## Hard invariants

- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass artifact or task text as shell arguments. Write to a temp file if a Bash command needs to read it; use `mktemp -u` so the Write tool creates it fresh.
- Non-zero Bash exit, unparseable reviewer response, or missing/invalid required field = hard abort. Never treat these as approval or revise.
- In `guided` mode (default), `AskUserQuestion` is called by the **orchestrator only** — never inside a sub-agent.
- Temp files created during a run must be removed on every exit path, including hard-abort paths.
- The audio-cue suppression marker (written by `say_skill_start`, removed by `say_skill_done`/`say_skill_cancel`) MUST be cleared on every exit path (normal finalize, cap/backstop finalize, and hard-abort) so a crashed loop never permanently silences the global Stop cue. Use `say_skill_done "$msg"` on paths that should speak; use `say_skill_cancel` on hard-abort paths where speaking is inappropriate.
