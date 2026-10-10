# implement-spec vs implement: review loop and invocation

## Question

Does `implement-spec` invoke the `implement` skill? How does each handle code review (trigger, reviewer, severity threshold, iteration cap, exit criteria, fixer, re-review, escalation)? What else differs, and what gaps or duplication exist?

## Short answer

**No.** `implement-spec` never calls the `implement` skill: no `Skill("implement")`, no textual reference, no copied logic. Its implementers call `tdd` (`skills/engineering/implement-spec/SKILL.md:38`). The only relation is a shared dependency on `code-review`, which both use differently.

`implement` runs a gated review loop: fresh-context reviewer, Critical/Major gate, re-review on every diff change, no iteration cap. `implement-spec` runs one `code-review` pass on the integration branch, then one implementer fixes "all issues" with no severity filter, no re-review, and no exit criterion.

Source files (all under `/Users/roman/projects/skills-dev/`):

- `skills/engineering/implement/SKILL.md` (74 lines)
- `skills/engineering/implement/review-brief.md` (27 lines)
- `skills/engineering/implement/render_review_brief.py` (91 lines)
- `skills/engineering/implement-spec/SKILL.md` (49 lines)
- `skills/dev/code-review/SKILL.md` (173 lines; the reviewer skill both rely on)

Both skills are installed as symlinks in `~/.claude/skills/implement` and `~/.claude/skills/implement-spec`, pointing into the repo. No copy was found elsewhere, so no plugin or other-location check was needed.

## 1. Does implement-spec invoke implement?

| Mechanism | Found? | Evidence |
|---|---|---|
| `Skill("implement")` call | No | Only `tdd` (L38) and `code-review` (L45) are named Skill-tool calls. |
| Textual reference to `implement` | No | The only `implement` strings in `implement-spec/SKILL.md` are its own name, "implementer subagents", and its description (L2-3, L15 and later). None names the `implement` skill. |
| Copied logic | No | Implement's Test/Review/Checklist/Commit steps and review brief do not appear. |
| Dependency doc | Indirect | `docs/agents/skill-dependencies.md:15` lists `implement-spec` → `to-spec` + `to-tickets` only. Line 13 says `to-tickets` recommends `/implement` ("Work the frontier one ticket at a time with `/implement`" in `skills/engineering/to-tickets/SKILL.md:152`). So the task-graph producer points to `implement`, not to `implement-spec`. |

Also: `implement-spec/SKILL.md:4` sets `disable-model-invocation: true`. `implement/SKILL.md` has no such flag. Both `agents/openai.yaml` files set `allow_implicit_invocation: false`.

## 2. Review loop, side by side

### implement

- **Trigger**: After Test passes. "Once done, run review in a fresh session..." (`implement/SKILL.md:18`). Fixed order: implement → test → review → checklist → commit (L6).
- **Reviewer**: `Agent({subagent_type: "general-purpose", ...})`, never `"fork"` and never an inline `Skill("code-review")` (L18). The agent calls `Skill("code-review", args="--build-cmd ...")` itself (`review-brief.md:11`).
- **Brief**: rendered by `render_review_brief.py`, passed verbatim (L18). Every `--check` must end in `?` (`render_review_brief.py:47-52`). Test evidence must match a count pattern (L25 `SUMMARY`, L33-37). `git add -N` new files first (L18).
- **Light review** (docs/comments only): effort `low` (L20).
- **Delta review** (re-review under 50 changed lines, no Critical/Major fix): `--diff-changed` names each fix, effort `low` (L22).
- **Severity threshold**: Critical/Major gate. "Review ends only when the **latest** report ... has zero Major/Critical" (L48). Minors: fix (then re-review) or list under "left as is" (L48, L35). Pre-existing Major/Critical on untouched lines: follow-up, out of scope (L35).
- **Verdict**: `Verdict: approve` when confirmed Critical and Major are both zero, whatever Minor count; `Verdict: request-changes` otherwise (`review-brief.md:26-27`). The line must be quoted; if absent, `SendMessage` the reviewer (`implement/SKILL.md:29`).
- **Gates before acting on report** (L24-31): hand-back frame arrived, completion notification arrived, `ListAgents` shows no review-started agent still running, `Verdict:` line quoted.
- **Re-review rule**: any diff change after the report, even a one-word docstring fix, gets a fresh review (L33). A fix after Review or Checklist re-enters at Test (L8).
- **Iteration cap**: none stated. Loop is implicit: review → fix → re-review until zero Critical/Major.
- **Who fixes**: not named explicitly; the implementing session triages and fixes (L35, L48). The reviewer does not edit.
- **Escalation**: no cap, so no escalation path. Unverifiable checklist items get an inline "Item not verifiable" note (L61). Post-merge work goes under `## On close` (`to-tickets/SKILL.md:127`). Ticket-code mismatch goes in the commit body as `Ticket vs code:` (L14).

### implement-spec

- **Trigger**: "Once all tickets are complete, call the Skill tool with `code-review` on the integration branch" (`implement-spec/SKILL.md:45`).
- **Reviewer**: the Skill call is named inline. No subagent wrapper, no fresh-context instruction, no brief template, no `--build-cmd`, no test evidence. Note that `code-review` is run in the calling session (or whatever session the skill runs in, see L15); ADR-0029 (`docs/adr/0029-code-review-step0-auto-isolation.md:28`) says "callers must wrap code-review in a subagent if isolation is required." `implement` follows this; `implement-spec` does not.
- **Severity threshold**: none. L45 says "Fix all issues raised by the code review," which includes Minor and Note-level items. No Critical/Major gate.
- **Max iterations**: none.
- **Exit / verdict criteria**: none. No `Verdict:` line check and no zero-finding requirement after fixes.
- **Who fixes**: "in a **single implementer subagent**" (L45).
- **Re-review**: none. The fix pass is not reviewed, and no delta rule exists.
- **Escalation**: none. Step 8 (L47) goes straight to "mark PR ready" or "resolve each ticket ... and report the integration branch."

### code-review (dependency both reference)

- Effort values are `low`, `medium`, `high`; default `high` (`code-review/SKILL.md:14`). `high` means fan-out plus adversarial verifier per Critical/Major finding (L14, L81).
- Verdict precedence: grade row, then any confirmed Critical/Major caps at REQUEST CHANGES, then zero confirmed Critical/Major means at least APPROVE WITH COMMENTS (L152).
- Docs-only mode (L76) exists for `implement`'s lineage tickets (`implement/SKILL.md:37`); `implement-spec` has no docs-only path.
- Mutating modes `autofix` and `review-to-merge` (L17, L113-115) auto-fix and commit. `implement-spec` L45 does not set `--mode`, so default `review` (read-only) applies. The fix pass is done by an implementer, not code-review.

## 3. Other differences

| Area | implement | implement-spec |
|---|---|---|
| Input | One ticket or spec (`implement/SKILL.md:3`) | Published spec plus task graph; preconditions stop if missing (`implement-spec/SKILL.md:19-26`) |
| Scope | Per ticket; ticket-level checklist and Status (L41-72) | Whole spec on one integration branch (L9) |
| Branch / worktree | `git switch -c <n>-<slug>` or worktree per AGENTS.md (L10) | Integration branch (L34); each implementer in own worktree (L36) |
| Test | `Skill("testing", args="--files ...")` after each change (L16); lint + covering tests; green summary line required (L8) | Implementer calls `tdd` only (L38); no testing skill, no lint gate, no green-line requirement |
| Checklist | Verify each `- [ ]` item, tick, set `## Status: done` (L46-66, ADR-0062) | None. Step 8 resolves tickets "the way the issue tracker closes work" (L47) |
| Commit | Stage by name, read `git diff --cached --name-only`, message rules, push, `Skill("pr")`, proof via `git ls-remote` / `gh pr view` (L68-72) | Merger subagent merges each implementer branch (L41); no commit or message rules; draft PR only if tracker uses PRs (L34) |
| Parallelism | Single-ticket, sequential | Frontier fan-out; background implementers in main conversation, foreground when run as subagent (L15, L43). Subagent mode is removed by ADR-0076: a reviewer at level 3 has no Agent tool |
| Cleanup | Not stated | Remove implementer worktrees (L49) |
| TDD | `/tdd` at each named seam (L12) | `tdd` for each ticket (L38) |

## 4. Gaps, inconsistencies, duplication

1. **Two review loops, no shared definition.** `implement` L18-48 and `implement-spec` L45 both dispatch `code-review`. They disagree on fresh context, threshold, re-review, and verdict. `implement-spec` L45 is the weaker copy.
2. **Inline `code-review` in implement-spec.** `implement/SKILL.md:18` forbids an inline `Skill("code-review")` call "in this session" because it reasons from what it wrote. `implement-spec/SKILL.md:45` does exactly that on the integration branch. The `code-review` skill also says callers must wrap it in a subagent (ADR-0029 L28).
3. **Fix pass not re-reviewed.** `implement-spec` L45 fixes everything in one implementer, then nothing. `implement` L33 requires a fresh review on any diff change.
4. **No severity threshold.** `implement-spec` L45 fixes Minor and Note items with no triage. `implement` L35/L48 requires triage and a "left as is" record.
5. **Effort not propagated (implement).** `review-brief.md:7` prints `Effort: {{effort}}` into the prompt, and `render_review_brief.py:77` accepts only `normal|low`. But `review-brief.md:11` calls `Skill("code-review", args="--build-cmd ...")` with no `--effort` flag. `code-review` therefore runs at its default `high` (`code-review/SKILL.md:14`). The light and delta review "effort low" from `implement/SKILL.md:20,22` does not reach `code-review`. `normal` is also not a `code-review` value (`low|medium|high`). Fix: pass `--effort` through in `review-brief.md:11`, or reword the brief.
6. **No iteration cap in implement.** Implement's loop has no cap or escalation. Non-convergence (a fix introduces a new Major each round) has no defined stop.
7. **implement-spec skips checklist verification.** ADR-0062 says implement's checklist workflow "acts as a consistency gate for ticket completion." `implement-spec` never ticks checklists or sets ticket `Status: done` in its own text. Implementers may run `tdd` only, so ticket Status may not update. Step 8 reads like "close the issue" without verification.
8. **implement-spec skips test gate.** No covering-test or lint run before merge; `tdd` only. The merger (L41) has no gate.
9. **Lineage (docs-only) tickets.** `implement` has a docs-only path (L37, code-review L76). `implement-spec` has no equivalent.
10. **Skill naming vs ADR refs.** `skill-dependencies.md:13,14` list `to-tickets` → `implement` and `implement` → `code-review`, but nothing lists `implement-spec` → `code-review`, `tdd`, or `testing`. The dependency doc is incomplete for `implement-spec`.
11. **Stale upstream sync.** `docs/research/upstream-skills-sync-2026-09-29.md:18,45` already flags `implement-spec` step wording as stale against upstream, with a "Port" item for Preconditions. The review-loop gap above is not in that note.
12. **Duplication risk.** The review-brief text (`review-brief.md`) is the single reviewer prompt. `implement-spec` L45 has no equivalent, so any fix in `implement` is not inherited. A shared brief or a call to `implement`'s review step from `implement-spec` would remove the duplicate.

## Recommendations

Decisions settled in review and recorded in [ADR-0076](../adr/0076-implement-spec-review-loop-and-per-ticket-implement.md) (items 1-5) and [ADR-0077](../adr/0077-pass-effort-through-to-code-review.md) (item 6). Both status: Proposed, pending critic review and user approval. No skill file has changed yet.

1. **Per-ticket work uses `implement`.** In `implement-spec/SKILL.md:36-39`, each implementer subagent calls `Skill("implement")` instead of `tdd`. The orchestrator brief overrides the end of `implement`: commit on the worktree branch, no push, no PR. Test, Review, and Checklist gates run as written. The checklist tick and `## Status` write run under the override; only the tracker ticket's seam text is untouched. Each implementer's `implement` run dispatches its own fresh reviewer, a nested dispatch. A file-based probe showed that agents at levels 1 and 2 have the Agent tool and level 3 does not (main session is level 0). The reviewer needs Agent for its `code-review` finders, so `implement-spec` runs in the main conversation only and refuses to run as a subagent (ADR-0076 Decision 1). Remove the subagent-mode wording at `implement-spec/SKILL.md:15,43`.
2. **Orchestrator lists the test seams.** Before dispatch, it passes a `Test seams:` list in the implementer brief. `implement` (L12) runs TDD at those seams. Implementers do not write seams into tickets; seam knowledge is spec-level and stays with the orchestrator. Each implementer's final result names one covering test per listed seam (`<seam>: <test>`, or `none` with a reason). The report is the implementer's evidence; the integration check verifies it against the merged diff. The orchestrator alone sets the spec's inline `Status`, once, after the integration review passes and every ticket merged. A partial run leaves it unset.
3. **Integration review is a gated loop.** Replace `implement-spec/SKILL.md:45` with: a Test gate on the integration tip before round 1 (`Skill("testing")`, green summary line quoted, passed in the round-1 brief); then a fresh `general-purpose` reviewer on the rendered brief at effort `high`, the Critical/Major gate, the `Verdict:` line, and re-review on any diff change. One integration fixer, using plain edits rather than `Skill("implement")`, fixes Critical/Major findings. A fix re-enters Test (`Skill("testing")`, green summary line) before re-review. Each integration review that ends with Critical/Major above zero is one round, and so is a re-review after a Minor-only fix. Fixer edits and Test gate fix passes are not rounds; the Test gate has its own 3-pass limit. Minors are fixed or listed as "left as is". Added check, one per seam, built from the implementers' reports: the reported covering test is in the diff and exercises the seam; a `none` entry is a Major finding unless its reason holds.
4. **Renderer takes a spec pointer and ticket list.** Extend `render_review_brief.py` with `--spec <pointer>` (optional) and repeatable `--ticket <pointer>`, where each pointer is an issue number or a file path. The brief reads each pointer: `gh issue view <n> --json body -q .body` for an issue number, the Read tool for a file path. Serves GitHub and local trackers. Integration checks are cross-ticket questions.
5. **Round limit, Test limit, and stop.** Both skills allow 3 rounds. A round is a review that ends with Critical/Major above zero, or a re-review after a Minor-only fix. In the per-ticket loop a delta review counts as a round; the integration loop has no delta reviews. Every Test gate allows 3 fix passes without a green summary line. `implement` does not commit and reports open findings or the failing test summary to the user. A blocked ticket is any dispatched ticket that returns without a commit, for any reason. `implement-spec` stops only the blocked ticket: it does not commit, its dependents stay undispatched, independent tickets finish and merge, and the integration review runs on the merged subset. If no ticket merged, the integration loop is skipped. A committed ticket branch that conflicts on merge counts as blocked; its GitHub issue already shows `done`, and it is not reverted automatically. The integration report lists the unmerged blocked and dependent tickets. The orchestrator reports. The spec's inline `Status` is not set to `done` on any partial run, and a draft PR stays draft. On a local tracker with no PR, blocked and dependent tickets keep their current `Status`, and the report names the integration branch, open findings, and unresolved tickets.
6. **Effort propagation.** Decided in ADR-0077: `render_review_brief.py` accepts `--effort high|low` (default `high`, `normal` removed); `review-brief.md:11` passes `--effort {{effort}}` to `Skill("code-review")`. `low` is a single inline pass (`code-review/SKILL.md:14`). Integration reviews always pass `--effort high`.
7. **Dependency doc.** `docs/agents/skill-dependencies.md` lists three edges, already added: `engineering/implement-spec` → `engineering/implement` (per-ticket work), `engineering/implement-spec` → `engineering/testing` (integration Test gate and fix re-test), and `engineering/implement-spec` → `dev/code-review` (integration reviewer, via the fresh agent). `implement-spec` calls `implement` and `testing` directly. It reaches `code-review` through the fresh reviewer agent.
8. **ADR.** ADR-0076 records items 1-5; ADR-0077 records item 6.
