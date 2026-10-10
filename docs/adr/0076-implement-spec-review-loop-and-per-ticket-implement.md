---
lineage-rules: exempt
---

# ADR-0076: implement-spec Delegates Tickets to implement and Runs a Gated Integration Review

**Status:** Decided  
**Date:** 2026-10-09  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

`implement` runs a gated review loop per ticket: Test gate before review, fresh `general-purpose` reviewer, Critical/Major gate, re-review on any diff change, checklist and Status gates (ADR-0029, ADR-0062). `implement-spec` does not call `implement`. Its implementer subagents call only `tdd`, so no ticket gets a test gate, a review, or a checklist tick. At the end it calls `Skill("code-review")` inline once on the integration branch, then one implementer fixes "all issues" with no severity gate, no re-review, no test re-run, and no round limit. ADR-0029 says callers must wrap `code-review` in a subagent.

Neither skill limits review rounds. `render_review_brief.py` accepts exactly one `--ticket` integer and the brief runs `gh issue view`, so it supports neither a whole-spec review nor a local tracker. Effort propagation to `code-review` is decided in ADR-0077.

Research: `docs/research/implement-spec-vs-implement-review-loop.md`.

## Decision

1. **Per-ticket work uses `implement`.** Each implementer subagent in `implement-spec` calls `Skill("implement")` instead of `tdd`. The orchestrator's brief overrides the end of `implement`: commit on the worktree branch, no push, no PR. The override removes only the push, PR, and proof steps. The Test, Review, and Checklist gates run as written. The implementer's worktree, created by the orchestrator on the integration branch, satisfies `implement`'s branch and worktree step. The merger subagent merges only branches that reached a commit, into the integration branch, as today.
   - **Nested reviewer dispatch.** Each implementer's `implement` run dispatches its own fresh `general-purpose` reviewer, as `implement` is written. The implementer is already a subagent, so that reviewer is a nested dispatch. A file-based probe (each level wrote its own file; main session is level 0) showed that levels 1 and 2 have the Agent tool and level 3 does not. The reviewer must spawn its `code-review` finders and verifiers, so it must sit at level 2 or above. **`implement-spec` therefore runs in the main conversation only.** Then the implementer is level 1, the reviewer level 2, and the finders level 3. When `implement-spec` runs as a subagent, the reviewer lands at level 3 with no Agent tool and `code-review` cannot run. The skill refuses to run as a subagent and says so. The probe result holds for this harness version and may change.

2. **Seams come from the orchestrator. Ticket seam text is not edited.** Before dispatch, the orchestrator reads the spec and the ticket and lists the test seams in the implementer brief under a `Test seams:` heading. `implement` treats seams in the brief like seams the ticket names (TDD runs only at named seams). No implementer writes seams into a ticket.
   Each implementer's final result names one covering test per listed seam, as `<seam>: <test id or path>`, taken from its own test run or grep. A listed seam with no covering test is reported as `<seam>: none` with the reason. The orchestrator passes these pairs to the integration review (Decision 3).
   The checklist step does write to the tracker. Under the override, each implementer ticks its own ticket's checklist and sets its `## Status` to `done` after its review gates hold, using `implement`'s ticket-location rules. For a local tracker, that edit sits in the repo file on the worktree branch and reaches the integration branch by merge. For a GitHub issue, the edit goes to the tracker before merge. The orchestrator alone sets the spec's inline `Status`; under the override each implementer skips checklist step 6, so concurrent implementers never write the spec. It sets it once, only when the integration review passes and every ticket in the spec merged (Decision 5).

3. **Integration review is a gated loop.** After all merges, the orchestrator runs this loop on the integration branch. When a blocked ticket left tickets unmerged, the loop runs on the merged subset. When no ticket merged, the loop is skipped (Decision 5).
   - **Test gate before round 1:** before the first integration review, the orchestrator runs `Skill("testing", args="--files <every path changed on the integration branch since its base>")` on the integration tip. The `testing` skill selects the covering tests and falls back to the full suite when a changed file is uncovered. The orchestrator quotes the green summary line and passes it to the round-1 brief as test evidence. If tests fail, the orchestrator sends the failures to the integration fixer. This fix pass does not count as a review round. The fixer fixes, re-runs `Skill("testing")`, and quotes the green line; the merger merges the fix; then round 1 runs. The Test gate limit applies (Decision 5).
   - **Reviewer:** a fresh `general-purpose` agent, never `"fork"`, never an inline `Skill("code-review")`. It takes its brief from `render_review_brief.py` (Decision 4) and calls `Skill("code-review")` itself, as `implement`'s reviewer does.
   - **Review kind and effort:** every integration review, round 1 and each re-review, is a full review at the default effort `high` (ADR-0077). The integration branch has no single-ticket scope, so `implement`'s light and delta review rules do not apply in this loop.
   - **Gates:** the four Review gates, the Critical/Major gate, the quoted `Verdict:` line, and re-review on any diff change, all as in `implement`.
   - **Checks:** the orchestrator adds one standard check per seam, built from the implementers' `<seam>: <test>` pairs: "Is the reported covering test for this seam in the diff, and does it exercise the seam?" A `none` entry is a Major finding unless the implementer's reason holds. The orchestrator also writes cross-ticket questions (for example, whether two tickets use the same interface).
   - **Fixer:** one implementer subagent, the integration fixer, fixes Critical/Major findings with plain edits in its own worktree on the integration tip. It does not call `Skill("implement")`. Minor findings are fixed in the same pass or listed "left as is" after the triage `implement` requires (`implement/SKILL.md:35`).
   - **Test gate before re-review:** a fix re-enters Test before the re-review. The fixer runs `Skill("testing", args="--files <changed paths>")`, quotes the green summary line, and passes that line to the re-review brief as test evidence, as `implement/SKILL.md:18` requires. Each re-review brief carries a fresh green line from the latest fix. The Test gate limit applies (Decision 5). The fixer commits on its branch with no push and no PR; the merger merges it.
   - **Counting:** the integration loop has its own round counter, separate from any per-ticket counter. Each integration review that ends with Critical or Major above zero is one round. A re-review after a Minor-only fix is also one round (Decision 5). Fixer edits and Test gate fix passes are not counted as rounds; the Test gate has its own limit (Decision 5).

4. **The review brief renderer takes a spec pointer and a ticket list.** `render_review_brief.py` gains:
   - `--spec <pointer>` (optional): the spec, as an issue number or a file path.
   - `--ticket <pointer>`, now repeatable: each value is an issue number or a file path. The existing single `--ticket <n>` call stays valid.

   A value of all digits is an issue number. Any other value is a file path, which must exist. The brief lists every pointer and tells the reviewer how to read each one: an issue number via `gh issue view <n> --json body -q .body`, a file path via the Read tool. No pointer is skipped. Integration checks are cross-ticket questions. No `--spec` flag accepts only GitHub issues.

5. **Round limit, Test limit, and stop.** A round is one review that ends with Critical or Major above zero, or one re-review run after a Minor-only fix. Both skills allow at most 3 rounds. In the per-ticket loop (`implement`, and each implementer in `implement-spec`), a delta review counts as a round. The integration loop has no delta reviews (Decision 3). The limit of 3 is a chosen bound on review cost: it allows two fix passes, each followed by a re-review. After the third round ends, no further fix pass runs. Minor findings left open are listed as "left as is." Every Test gate allows 3 fix passes without a green summary line. When a Test gate reaches that limit, the stop below applies, and the stop report includes the failing test summary. The reporter is the orchestrator, the session running the skill. Its final report goes to the user in the main conversation.
   - **`implement`, single ticket:** does not commit. The worktree and branch stay in place with the uncommitted changes. It reports the open findings (or the failing test summary) to the user and waits.
   - **`implement-spec`, blocked ticket:** a blocked ticket is any dispatched ticket that returns without a commit, for any reason: a round-limit stop, a Test gate limit, or a subagent failure. The blocked implementer does not commit. It returns a stop report as its final result: open findings or failing test summary, branch, worktree path, and the tickets it blocks. If the subagent returns no stop report, the orchestrator writes one. The orchestrator reads that result, so no wait channel is needed. The merger skips the blocked ticket. Its dependents (direct or transitive `Blocked by`) are not dispatched and stay unresolved. Independent frontier tickets continue and merge. Cleanup (step 9) keeps the blocked ticket's worktree for inspection.
   - **Committed ticket that fails to merge:** a ticket branch with a commit that conflicts on merge counts as blocked. Its GitHub issue already shows `done`, because `Status` was set before merge. Do not revert it automatically. The report notes that the issue shows `done`.
   - **`implement-spec`, integration review after a blocked ticket:** the integration loop (Decision 3) still runs, on the merged subset. Its brief passes only the merged tickets as `--ticket` pointers. If no ticket merged, the integration loop is skipped. The integration report lists every blocked ticket with its open findings and worktree path, and every undispatched dependent with the ticket that blocks it.
   - **`implement-spec`, integration stop:** the integration loop stops. The report lists the open findings, the integration branch, and the tickets not merged. Merged tickets keep `Status: done`. The report lists each done ticket that has open integration findings.
   - **Partial run:** when any ticket is blocked or undispatched, or no ticket merged, the run is partial even if the integration review passes on the merged subset. The orchestrator does not set the spec's inline `Status` to `done`, and it does not mark a draft PR ready. The report names every unresolved ticket.
   - **Outcome by tracker:**
     - Draft PR exists (tracker uses PRs): the PR stays draft after an integration stop or a partial run.
     - Local tracker, no PR: blocked and dependent tickets keep their current `Status`, not `done`. Tickets already `done` keep `done`. The spec's inline `Status` is not set to `done`. The report names the integration branch, the open findings, and the unresolved tickets.
     - GitHub issue, no PR: the issue stays open. Closing it waits until its commits reach the default branch (`implement` skill, **After the commit**), a step the user performs.

6. **Effort propagation** is decided in [ADR-0077](0077-pass-effort-through-to-code-review.md).

## Considered Options

- Keep `tdd` per ticket and copy the Test and Checklist gates into `implement-spec`: rejected, it duplicates the gates and drifts from `implement`.
- Run one review at integration level only: rejected, per-ticket review catches defects before they merge with other work.
- Add a `--spec` flag that accepts only a GitHub issue: rejected, it would not serve the local tracker and differs from `--ticket` only in what the reviewer reads.
- Write seams into the ticket: rejected. Seam knowledge is spec-level, and the orchestrator's single view of the spec should own it. A seam list per ticket would split that knowledge across tickets and make each implementer re-derive the spec to find its seams.
- Implement reads ticket seams unchanged, with no orchestrator seam list: rejected. A ticket may name no seam, and the orchestrator's spec-level view would then never reach the implementer.
- Drop the per-seam `<seam>: <test>` report and let the integration reviewer find covering tests itself: rejected. The report is the implementer's evidence, taken from its own test run. The integration check verifies that evidence against the merged diff. Without the report, the reviewer must search for tests with no claim to confirm or refute.
- Call `Skill("implement")` for the integration fixer: rejected, the nested `implement` keeps its own round counter, so the integration work would have two counters.
- Light or delta reviews in the integration loop: rejected. The integration branch has no single-ticket scope, and a low-effort pass drops the adversarial verifier on the review that sees all tickets together.
- Run the first integration review with no Test gate: rejected. Merges can break tests that each ticket passed alone, and the brief needs test evidence, as in `implement`.
- Stop the whole run at the first blocked ticket: rejected, independent tickets still need review and merge, and one blocked ticket would discard their work.
- No round limit: rejected, a fix that adds a new Major each round never ends.

## Consequences

- Each ticket pays for its own fresh-agent review, so a spec with N tickets runs at least N+1 reviews. Every integration review runs at effort `high`. The integration loop adds one Test gate before round 1 and one per fix round.
- TDD in `implement-spec` shrinks from every ticket to the seams the orchestrator lists. The orchestrator must list them.
- Seam omission: a seam left off the list gets no TDD. Three checks back the list, and each covers a different point. The implementer's `<seam>: <test>` report is its evidence, from its own test run. The integration seam check verifies that evidence against the merged diff, after other tickets may have changed the code. The per-ticket review checks the ticket's code before merge. Accepted risk: a behavior the orchestrator never listed as a seam can still merge without a covering test. The reports prove coverage of listed seams only.
- The implementer's final result gains a required `<seam>: <test>` list, and the orchestrator builds one integration check per seam from it.
- `implement` gains the commit-only override contract (no push, no PR) and the stop on the round limit or Test gate limit (no commit). The skill text must state both.
- Under the override, GitHub issue checklists and Status change before the merge to the default branch.
- `implement-spec` can no longer run as a subagent. The text in `implement-spec/SKILL.md:15` about launching implementers in the foreground when the skill runs as a subagent is removed, and the skill refuses to run below the main conversation.
- A local tracker's spec and ticket files reach the integration branch by merge only when git tracks them. This repo ignores `.scratch`, so there the orchestrator passes absolute pointers into the main checkout to `render_review_brief.py` instead of relative ones.
- A partial run leaves the spec's inline `Status` unset and any draft PR in draft, even when the integration review passes.
- `docs/agents/skill-dependencies.md` lists three new edges (already added):
  - `engineering/implement-spec` → `engineering/implement` (per-ticket work).
  - `engineering/implement-spec` → `engineering/testing` (integration Test gate before round 1 and fix re-test).
  - `engineering/implement-spec` → `dev/code-review` (integration reviewer, through the fresh agent).
