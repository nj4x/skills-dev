# Code Review Workflow: Mutating Modes

Disclosed from [workflow.md](workflow.md). Read when `REVIEW_MODE_AUTONOMOUS = YES` (`--mode autofix` or `review-to-merge`); read nothing here for `--mode review`. Step numbers match the references in workflow.md and SKILL.md.

---

## Step 4.1-RTM: Four-Agent Review Profile (mutating modes only)

> **Mode gate**: Runs only when `REVIEW_MODE_AUTONOMOUS = YES` (`--mode autofix` or `review-to-merge`). In that case this profile **replaces** the 4 A/B/C/D finders of Step 4.1 — do not run both rosters. Effort is forced to `high`, so Step 4.2 adversarial verification always follows.

Spawn 5 Explore agents **in parallel**, per the Step 4.1 dispatch rule (READ-ONLY for this discovery phase). Pass each agent the same inputs as Step 4.1 (full diff, `PROJECT_SRS`, `PROJECT_API_DEFINITION`, `PROJECT_MODULE_VIEW`, `PROJECT_DATA_VIEW`, the `--scope` value). The five angles isolate **Tests/Regressions** and **Operational risk** as first-class lanes because the mutating path will *write* regression tests and *merge*. Smells run in their own dedicated agent so they never inflate the per-agent context of the functional review lanes.

### Agent 1 — Correctness & Edge Cases

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Correctness & Edge Cases**: logic bugs, off-by-one and boundary conditions, null/empty/overflow handling, incorrect error handling, removed behavior callers rely on, stale-data risks, race conditions, data mutation from ambiguous input.
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix`. Omit findings you are not confident about.

### Agent 2 — Tests & Regressions

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Tests & Regressions**: missing coverage for changed paths, regressions introduced by the diff, brittle/flaky tests, test gaps per changed function, framework/standards adherence (Kotlin Test over JUnit, MockK `match {}` vs `any<T>()`; pytest patterns for Python), test independence, event-exhaustiveness checks. For each changed function lacking a regression test, name the test that should exist.
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix` (or the missing test to add). Omit findings you are not confident about.

### Agent 3 — Architecture & Maintainability

Apply the shared **Deep-Module Lens** ([deep-module-lens.md](deep-module-lens.md)).

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angles are **Architecture & Maintainability** and **Deep-Module Detection**.
>
> First read `~/.claude/skills/code-review/docs/deep-module-lens.md` — it contains the pre-read list, bounded-context rule, and the two deep-module detection scenarios; apply them exactly.
>
> **Architecture & Maintainability:**
> - Module boundary violations, circular dependencies, wrong-layer access, field-injection anti-patterns, duplication that should be extracted
> - Naming, complexity, dependency direction, dead code, over-engineering
> - N+1 queries, missing pagination, DynamoDB Limit+FilterExpression misuse
> - API + Data View compliance when PROJECT_API_DEFINITION / PROJECT_DATA_VIEW is provided and the diff touches controllers/API models or DDB entities/repos/configs: grade per the severity policies and allowances in workflow-compliance.md Steps 8.x.1, 8.y, 8.5.1, and 8.5.2 — read them before grading any API-doc or Data View mismatch.
>
> **Deep-Module Detection:** apply the two scenarios from the shared lens (deep-module-lens.md).
>
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR/POSITIVE), `file:line`, `description`, `recommended fix` (or `what's good` for POSITIVE). Omit findings you are not confident about.

### Agent 4 — Security & Operational Risk

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Security & Operational Risk**: hardcoded secrets/tokens, PII in logs, SQL/command injection, weak auth, insecure CORS, exposed internals — PLUS operational concerns relevant to autonomously merging this change: migration/rollback safety, config and feature-flag risk, idempotency, observability/logging gaps, and merge-safety (anything that would be unsafe to land on main).
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix`. Omit findings you are not confident about.

### Agent 5 — Maintainability Smells

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Maintainability Smells** from Fowler's _Refactoring_, chapter 3.
> First read `~/.claude/skills/code-review/docs/smell-baseline.md` — the canonical 12-smell catalogue and its binding rules (repo overrides baseline, skip tooling-enforced smells, Notes-only, judgement-call standard). Apply them exactly.
> **De-dup precedence for this roster:** skip a `file:line` if Agents 1, 2, 3, or 4 already reported it at any severity.
> For each finding return: `severity = NOTE`, `file:line`, `smell name`, `description`, `suggested fix`. Omit findings you are not confident about.

### Synthesis (shared)

Reuse the Step 4.1 **Synthesis** and **Mandatory Pre-Report Verification Protocol** blocks verbatim (merge, dedupe by `file:line` keeping higher severity with Agent 5 Notes always losing to any Agent 1–4 finding at the same file:line; sort CRITICAL → MAJOR → MINOR → NOTE → POSITIVE; Agent 5 Notes are never sent to the adversarial verifier). Then proceed to Step 4.2 (adversarial verification — always runs, effort is `high`).

---

## Step 14: Autonomous Mutating Modes (`--mode autofix` / `review-to-merge`)

> **Mode gate**: This step runs **only** when `REVIEW_MODE_AUTONOMOUS = YES`. In `review` mode the workflow ends after the report (and Step 13.5 when PR integration is active).
>
> ⛔ **Prerequisite (non-bypassable)**: do not begin any RTM phase until the report (Step 13) exists and every read-only gate is resolved (Step 1/1.5 branch+divergence, Step 1.5 PR-context, Step 2 build with `BUILD_STATUS` **not** `FAILED` or `WAIVED`, Step 4.1-RTM + 4.2 verification). See the "RTM/Autofix prerequisite" block under *Non-negotiable execution order*. If `BUILD_STATUS` is `FAILED` or `WAIVED`, report and STOP — do not mutate.

This step inverts the skill's read-only default: it implements fixes, writes tests, commits, and (for `review-to-merge`) pushes and merges. All mutation is gated.

### Design decisions: iteration caps and exit behavior

| Loop | Cap | Exit behavior when cap is hit |
|------|-----|-------------------------------|
| Fix-implementation attempts per finding | **3** | Mark that finding `UNRESOLVED`, revert/leave its code untouched (see recovery rows), continue remaining findings, surface it in the final summary as needing manual attention. Never blocks other fixes. |
| Full-suite debug re-runs after fixes applied | **3** | STOP. Do not commit (if uncommitted); if commits already made, do not push/merge. Report failing tests, the loop's commit SHAs, and recovery options. Terminal stop — no auto-merge, no further retries. |
| Adversarial final-review passes (RTM-6) | **2** | If an accepted Major/Critical is still unaddressed after 2 passes, STOP before push/merge; report the gap. |
| Critic passes over the fix plan (RTM-2) | **fixed 3** (impossible-assumptions, missing-deps/schema-mismatch, test-gap) | Bounded analysis, not a retry loop — run exactly the three, then proceed. No cap-exhaustion state. |

**Exit-state guarantee:** whenever any cap is hit, the terminal state is "report + stop," never push or merge. The only path to push/merge is a fully green suite + a clean adversarial final review + the consent gates below.

### Consent model: BLOCKING gates

- **announced (informational):** the agent prints a banner of what it is about to do; no user reply required. Used for non-mutating progress (e.g. "entering RTM-3, implementing 4 fixes").
- **BLOCKING consent gate (hard gate):** the agent prints the exact git command + target, then STOPS and waits for an explicit user reply before executing. It does not proceed on silence, does not infer consent, and does not batch multiple mutating actions behind one approval. Same force as the Step 1.5 "print verbatim then wait" gate.

| Action | Gate | Default |
|--------|------|---------|
| Commit (RTM-5) | BLOCKING | Explicit confirmation before `git commit`. No auto-proceed. |
| Push (RTM-7) | BLOCKING | Explicit confirmation before `git push`. No auto-proceed. |
| Merge to main (RTM-7) | BLOCKING | Explicit confirmation before merge. No auto-proceed. |

**Operator pre-authorization:** a session may run under "Auto Mode"; the operator MAY pre-authorize specific actions up front (e.g. "autofix and commit without stopping"). When pre-authorized, that gate is satisfied without a per-action pause, but the banner is still announced. **Merge to main is never implicitly auto-authorized** — it always requires a per-action confirmation or an explicit "merge to main without stopping" instruction.

### Phases

**RTM-1 — Status/branch/upstream/scope confirmation.** Confirm `git status`, current branch, upstream tracking, and review scope (reuse Step 1 outputs). If branch/upstream/scope is unclear, default to the safe interpretation — committed scope on the current non-`main` feature branch — and state the assumption. If on `main`, state it immediately, propose a feature branch, and block (do not mutate `main`). **Capture the pre-RTM HEAD SHA** as the rollback anchor for every recovery row.

**Scope-specific handling:**
- **`--scope committed`** (default): fixes are committed as new commits on the feature branch per RTM-5.
- **`--scope working-tree` (or its alias `uncommitted`) + `--mode autofix`**: this is a naturally supported combination. Review the working tree, implement fixes on top of the existing uncommitted work, and commit the reviewed changes **plus** the fixes together at RTM-5 behind the normal BLOCKING consent gate. Do NOT hard-block or ask the user to switch scope — the uncommitted work under review is the intended commit content. The BLOCKING gate at RTM-5 is where the user reviews the exact staged set before confirming; print `git status` there so the staged set is visible.
- **`--scope working-tree` + `--mode review-to-merge`**: the merge step (RTM-7) requires committed-scope semantics and a feature branch. Run review + autofix + commit as above, but before RTM-7 confirm a non-`main` feature branch exists; if only `main` is present, STOP after commit and report (do not merge working-tree fixes straight to `main`).

**RTM-2 — Consolidate fix plan + 3 critic passes.** From the Step 4.1-RTM / 4.2 verified findings, filter to Major/Critical and build an ordered fix plan (each entry: finding id, `file:line`, root cause, proposed fix, regression test to add, dependencies/order). Quarantine any finding that requires a genuine product decision — these are the only stop-for-user items in the loop. Then run the three fixed critic passes over the plan (reuse the Step 4.2 adversarial style, retargeted at the plan): (1) impossible assumptions, (2) missing dependencies / schema or contract mismatches (cross-check `PROJECT_DATA_VIEW` / `PROJECT_API_DEFINITION` / `PROJECT_SRS`), (3) test-coverage gaps. Drop or rewrite plan items the critics refute.

**RTM-3 — Implement fixes + regression tests + selective suite.** Per accepted finding: implement the fix following the relevant standards docs (kotlin/python/testing/security/architecture), one logical change per fix, traceable to a finding id; add or update a regression test that fails before and passes after (3-attempt cap per finding). After all fixes, run the tests via the `testing` skill's selective runner (`--files <changed files from review scope + fix-touched files>`); the testing skill maps those files to their covering tests and **falls back to the full suite automatically when any changed file has zero coverage**, so the safety net is preserved without code-review implementing its own. Loop: if any test fails → debug → re-run, within the 3-rerun cap. Hard rule: do not proceed to commit while the run is red. The user may request a full-suite run explicitly. This is the autonomous fix flow from `~/.claude/CLAUDE.md` (identify Major/Critical → implement → regression tests → run relevant tests → debug to 100% → structured commit), stopping only for genuine product decisions.

**RTM-4 — Summarize changes.** Produce a structured summary: each finding → its fix → its regression test → suite result.

**RTM-5 — Commit (BLOCKING consent gate).** Stage ALL changes per the global git convention (modified files + renames + new files; never a partial set). For `--scope working-tree`/`uncommitted` this stages the reviewed uncommitted work together with the autofixes — that combined set is the intended commit. Print `git status` as part of the BLOCKING banner so the user sees the exact staged set before confirming. Use a structured commit message listing each finding and its fix, with the `Co-Authored-By` trailer. See git-commands.md for the message format. **`autofix` terminates here** — report the commit SHA and summary.

**RTM-6 — Adversarial final review (≤2 passes).** Re-run adversarial verification against the **original** finding list: for each original Critical/Major, confirm it is now actually resolved (`CONFIRMED-FIXED` / `STILL-OPEN` / `REGRESSED`). Also scan the implemented diff for *new* findings (regressions, new security/operational risk). If anything is `STILL-OPEN`, `REGRESSED`, or a new Critical/Major appears → return to RTM-3 (bounded by the cap) or, if the cap is hit, STOP before push and report the gap + commit SHA.

**RTM-7 — Push (BLOCKING gate) then safe merge to main (BLOCKING gate).** Push the feature branch (BLOCKING). Then re-evaluate the merge-safety gate: tests green, RTM-6 clean, branch not behind base (re-fetch base), no conflicts, no-merge-without-consent honored. If safe and confirmed: if a PR exists, merge via the existing PR/repo workflow; otherwise merge the working branch into `main` per the global convention (see git-commands.md). If any safety condition fails → STOP after push, report exactly what blocked the merge, do not force. Record the audit trail: commit SHA, pushed branch, merge result/URL. **`review-to-merge` terminates here.**

---

## Error Handling (mutating modes)

- `BUILD_STATUS` is `FAILED` or `WAIVED` at the prerequisite gate → report and STOP; do not start the mutating path (mutation on an unverified baseline is unsafe).
- Suite 3-rerun cap hit, **commits already made** → (1) run `git log <pre-RTM-sha>..HEAD` and report the exact loop SHAs; (2) offer a concrete revert command (`git revert <sha>...` or `git reset --hard <pre-RTM-sha>` with an explicit warning) — do NOT auto-execute; (3) NEVER push/merge. Terminal stop.
- Suite cap hit, **no commit yet** → leave the working tree as-is, report applied vs failing fixes, offer a discard option (`git restore <files>`) — do not auto-discard. NEVER commit.
- Single finding unresolvable in 3 attempts → revert that finding's partial edits (or leave untouched if not yet written), mark `UNRESOLVED`, continue other findings.
- RTM-6 finds an unaddressed accepted finding (`STILL-OPEN`/`REGRESSED`) after the cap → stop before push/merge; report the gap + commit SHA.
- Merge unsafe at RTM-7 (conflicts, protected branch, branch behind base, failing CI on main) → stop after push (branch pushed, mergeable state reported); report why; never force.
- Product-decision finding encountered during the loop → stop and ask the user (the only mandatory blocking question inside the autonomous loop).
