# Autonomous Mode — Full Reference

When `/continue` is invoked in **autonomous mode**, drive the next incomplete phase to a committed, fully-tested state without stopping for user choices. Use `TaskCreate`/`TaskUpdate` to surface progress. Follow these six steps in order.

## Step 1 — Discover State

Read the project's state-bearing files and recent history to determine exactly where the project is and what the next phase requires:

- Read `CLAUDE.md` (project instructions, coding standards, current phase, next phase).
- Read the task/state file (`task.md` or the project's equivalent — check `CLAUDE.md` for the canonical name).
- Run `git log --oneline -10` to see what was last completed.
- Identify the **next incomplete phase** and its requirements from the spec or implementation plan.

Summarize findings concisely; do not dump raw output into context.

## Step 2 — Plan with Critic

Write a detailed implementation plan for the next phase to the project's task/state file. Then **critique your own plan** before executing it. Check for:

- Spec violations (SRS, API Definition, Data View, Module View, and project invariants)
- Missing edge cases
- API mismatches with existing code (signatures, schema field names, event counts, entity fields)
- Impossible or contradictory operations

Revise the plan until it is sound. If a `plan-with-critic` skill is available, prefer delegating this step to it.

## Step 3 — Implement

Execute the plan across all necessary files. Decompose the phase into independent units (no shared-file dependencies). When ≥3 independent units exist (advisory floor — fall back to serial if units share heavy context), launch one Agent subagent per unit **in a single message** so they execute in parallel; each subagent implements and tests its unit, writing only to files it owns. After all report back, run a reconciliation pass: cross-unit consistency (signatures, imports, shared contracts), then proceed to the test step. If any subagent fails, implement its unit serially. The Step 4 self-heal loop always runs sequentially in the main conversation — never parallelize test-fix cycles.

Follow the project's coding standards exactly (e.g., `~/.claude/skills/code-review/docs/python-standards.md` for this project).

## Step 4 — Test and Self-Heal

Run the full test suite. **If tests fail, enter the self-heal loop (max 5 cycles):**

a) Read the failure output carefully.  
b) Identify the root cause (API mismatch, missing import, logic error, fixture problem).  
c) Apply the **minimal** fix targeting that root cause — do not bandage symptoms.  
d) Re-run the test suite.  
e) Repeat from (a).  

Surface to the user **only** if:
- 5 cycles elapse without all tests passing, OR
- a fix requires a genuine product decision (resolve all other ambiguity by reading the codebase and specs yourself).

Write a regression test for each new behavior or fix. Do not mark the phase done while any test fails or any implementation is partial.

## Step 5 — Commit

When **all** tests pass, stage all changes (`git status` first; stage modified, renamed, and new files together — never a partial set) and commit with a structured message:

```
feat: [phase name] — [N] files changed, [M] tests passing, [K] new tests added
```

Follow the project's git norms (no `--no-verify`; create a new commit rather than amending).

## Step 6 — Update State and Hand Off

Update the task/state file to mark this phase complete and summarize what was built. Then ask the user:

> Phase X complete. Shall I proceed to Phase Y autonomously?

This is the one expected stopping point on the happy path. If the user has explicitly authorized chaining multiple phases without confirmation, proceed to the next phase's Step 1 instead.

## Example: Self-Heal Cycle

```
Phase 6.7 — Implement orchestrator workflow.

Cycle 1: Run pytest → 12 failures
  Root cause: OrchestratorConfig missing `max_retries` field used in 12 tests.
  Fix: Add `max_retries: int = 3` to OrchestratorConfig schema.
  Re-run → 4 failures.

Cycle 2: 4 failures in test_workflow_routing.py
  Root cause: WorkflowRouter.__init__ expects (config, adapters) but tests pass (adapters, config).
  Fix: Swap parameter order to match existing call sites (confirmed via grep).
  Re-run → 0 failures. All 341 tests pass.

Commit: feat: Phase 6.7 Orchestrator — 8 files changed, 341 tests passing, 26 new tests added
```

## Guardrails

- **Fail-closed on safety:** never weaken kill switches, safety gates, or the no-live-order default to make a test pass. A failing safety test means the implementation is wrong, not the test.
- **No `--no-verify`, no destructive git** (reset --hard, force-push) to clear obstacles. Fix root causes.
- **Resolve ambiguity by reading**, not by asking — specs, existing code, and git history first. Only a true product decision or a 5-cycle stalemate justifies interrupting.
- **One commit per phase** on the happy path, after the full suite is green with zero regressions.
