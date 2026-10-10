---
name: implement
description: "Implement a piece of work based on a spec or set of tickets. Use when the user says 'implement this', 'build this', agrees to a fix or change the agent proposed (after research or diagnosis, a bare 'yes' counts), or wants a ticket or spec worked through to a tested, reviewed state."
---

Fixed order, no step skipped or reordered: implement → test → review → checklist → commit. Reaching "ready to commit" without having run the checklist step is a process error, not a shortcut — go back and run it.

Each step ends on a gate defined below: Test, the testing skill's green summary line for the covering run; Review, every gate under **Review is complete**; Checklist, the review report's `Verdict:` line is quoted, re-reading the ticket shows zero `- [ ]`, and `## Status` reads `done`; Commit, every rule under **When committing** and **After the commit**. A fix found after Review or Checklist ended re-enters at Test and runs each later step again.

Run `git branch --show-current` and `git status --short` before the first edit; on the default branch, `git switch -c <n>-<slug>` first, so every commit and push lands on a feature branch. When the repo's AGENTS.md calls for worktrees, enter one before any branch or edit, whatever `git status` shows. Otherwise, modified or untracked files you did not write mean a shared working tree: enter a worktree (`EnterWorktree`, then run the worktree bootstrap the repo's AGENTS.md names, if any) so the commit holds only this ticket's hunks, or record the foreign paths now and stage by hunk (testing skill) at commit. At commit time, verify `git diff --cached --name-only` matches the files named in the commit message (or the message lists "unrelated concurrent changes"); if not, investigate — foreign hunks slip into the index unnoticed.

Use /tdd at every seam the ticket or spec names explicitly (look for a "Test seams" or "Acceptance criteria" section) and at every seam the brief that started this run lists under `Test seams:`. When the brief lists seams, end your final result with one `<seam>: <test id or path>` line per listed seam, taken from your own test run or grep; a seam with no covering test reads `<seam>: none — <reason>`.

Before designing, check the ticket's stated root cause or premise against the code. When the code contradicts the ticket, record the mismatch in the checklist note and in the commit message body as a `Ticket vs code:` line (`none` when the code matches the ticket), and write the commit message from what the code shows. Ticket-code mismatches: always record in final report and commit body so future readers know what was claimed vs. what was built.

After each substantive change, run typechecking and the test file(s) that cover that change via `Skill("testing", args="--files <changed paths>")` — selective runner maps changed source files to covering tests, falls back to full suite only for uncovered files. A Test step with no green summary line after 3 fix passes is a stop (see **Round limit and stop**).

Once done, run review in a fresh session that inherits none of this session's context: `Agent({subagent_type: "general-purpose", ...})` — never `"fork"` (a fork inherits this session's context and can skip the fan-out, reasoning from memory instead of actually reading the diff) and never an inline `Skill("code-review")` call in this session (same problem: it reasons from what it already wrote, not from a fresh read). Render the brief with `python3 ~/.claude/skills/implement/render_review_brief.py --ticket <n> --worktree <abs path> --branch <branch> --git "<git binary>" --build-cmd "<lint> && <type-check>" --test-evidence "<test summary line>" --check "<requirement>" [--check ...]` and pass its stdout verbatim as the agent prompt ([review-brief.md](review-brief.md) holds the fixed text); a re-review reruns it with `--diff-changed "<what changed and why>"`. Each `--check` is a ticket requirement, a decision beyond the ticket, or a cross-file rule, stated as a question the reviewer answers from code, never as a claim about the diff. Run `git add -N <new files>` first: an untracked file is absent from `git diff HEAD`, and the reviewer cannot review what the diff omits. Dispatch review only on a tree with no edit since the Test step's last green run, and quote that run's summary line, verbatim from the test runner (scope worded as the testing skill words it) in the brief as the test evidence: the build gate re-runs lint and type check, never the covering tests a second time. Any edit after that run re-enters Test first. Code-review's build gate is a mandatory guard.

A diff that touches only docstrings, comments, message strings, and docs is a **light review**: brief the agent with `--effort low`, hand it the diff, and have it verify each factual claim in the changed text against the code it names. The fresh session, `Skill("code-review")` call, and build gate are unchanged.

A re-review whose delta is small — under 50 changed lines, none of it fixing a Critical or Major finding — is a **delta review**: brief the agent with `--effort low` and `--diff-changed` naming each fixed finding and the symbols touched, and have it verify each fix, read the diff of those symbols only, and state that no other symbol changed. The fresh session, `Skill("code-review")` call, and build gate are unchanged. The last full report (zero Critical/Major, by this definition) plus a clean delta report together satisfy the latest-report rule of **Verify-then-check checklist workflow**. A delta that touches only docstrings, comments, message strings, and docs is a light review.

**Review is complete** when every gate holds:

- The hand-back frame arrived: a message from the agent that holds the report, build gate resolved green or red. The report's text comes from this frame.
- The completion notification arrived: a signal only, it repeats nothing.
- `ListAgents` shows no agent started during the review still running. The reviewer's own finders and verifiers also notify this session, and a hand-back that arrives first can quote a finder verdict before that finder has returned.
- The report's final line is the `Verdict:` line [review-brief.md](review-brief.md) requires, quoted. When it is absent, `SendMessage` the reviewer to restate it.

The four gates hold on every round, a re-review included. While they are pending, run read-only checklist verification. Ticking an item and setting `## Status` to `done` are writes: do them after the gates hold.

**Re-review on any diff change**: code that changes after the review report arrives (even a one-word docstring fix for a Minor finding) gets a fresh review session against the new diff, and the four gates hold again before the first checklist edit.

Triage every finding against the code before acting. A Major or Critical finding on a line the diff does not touch is pre-existing: file it as a follow-up and keep it out of this change. A Minor you do not fix is "left as is" only after you read or grepped the code the reviewer cited; record the triage note in the final report.

A ticket that changes no code (a lineage ticket: ADRs, requirements, docs) still runs every step. Its Test step is lint only (the testing skill's docs-only rule), and code-review runs in its docs-only mode. The ticket's checklist still governs what "done" means — authoring the ADR is not done when the checklist also asks for FS merges or ticket-body updates.

## Round limit and stop

A **round** is one review whose report has Critical or Major above zero, or one re-review run after a Minor-only fix. A delta review counts as a round. Allow at most 3 rounds. Three is the first value that allows one fix and one re-review after a failed round.

After the third round ends, run no fix pass. When its report has zero Critical and zero Major, the review is complete: list the open Minor findings as "left as is". Otherwise, stop.

Every Test step allows 3 fix passes without a green summary line. At that limit, stop.

**Stop**: do not commit. Leave the worktree and branch in place with the uncommitted changes. Report the open findings (or the failing test summary), the branch, and the worktree path, then wait for the user. When an `implement-spec` brief started this run, return the same facts plus the tickets this ticket blocks as your final result and end; the orchestrator reads it.

## Ticket location

Resolve where each ticket's checklist and Status field live before the checklist workflow, and use that same location for every edit in that workflow:

- **Ticket is a repo file** (e.g. `.scratch/<slug>/draft-issues/*.md`): edit the file directly.
- **Ticket is a GitHub issue** (see the project's `docs/agents/issue-tracker.md` if present): read it with `gh issue view <n> --json body -q .body`, and read that doc before the first checklist edit: when it names a ticket-check script, use the script to tick items and set Status, never a hand-built body. Without a script, edit the fetched body text with `gh issue edit <n> --body-file <tmp>`, keeping every section (a body rebuilt from only the touched sections drops the rest). Closing the issue (`gh issue close <n>`) is a separate, later action — see that doc for when it applies; it is not part of this checklist workflow.

## Verify-then-check checklist workflow

This phase runs after code-review produces zero Major or Critical findings, and before any commit. Review ends only when the **latest** report — on the diff as it stands after your fixes — has zero Major/Critical; fixing findings and moving on without a fresh report against the final diff is the same process error as skipping Review outright (see **Re-review on any diff change**). Triage each Minor finding before the checklist: fix it (and re-review) or list it under "left as is" in the final report.

For each ticket completed in this implementation effort:

1. Extract all `- [ ]` checklist items from the ticket (see Ticket location above).
2. For each unchecked item, **verify** that the work is done:
   - Run named test(s) if the item identifies test IDs.
   - Inspect code if the item describes behavior but no named test exists.
   - Check output, logs, or observable state if the item is output-observable.
   - A lint or gate item is checked only against the exact command and scope you ran. When a repo-wide run fails in files outside your diff (someone else's uncommitted work), record `clean for changed files; pre-existing failures: <paths>` in the note, and re-run the repo-wide command before commit, since the pre-commit hook runs it.
   - Record the verification method as a brief note (e.g., `test <test-id> passed`, `code: see ClassName.method`). Take every test name and symbol from your own run or grep, never from the review report.
   - When you verify work against code, re-grep the symbols you cite to confirm they still match the final diff; line numbers shift and references rot.
3. If verification succeeds: rewrite the item as `- [x] <original text> — <verification note>`. Keep every item and its original text verbatim; an item for a branch not taken (e.g. "If fix: …" when the decision was document-only) becomes `- [x] <original text> — n/a: <branch chosen>`, never merged or dropped. An optional item is a branch too: tick it `n/a: <reason>`. Name code in notes by symbol, never `file:line`; line numbers shift with each diff and rot afterward. Re-grep every symbol or path you cite in the note and the commit message against the final diff before writing it.
4. If an item cannot be verified (no test, no inspectable code, no observable output): do **not** check it. Append an inline comment: `— Item not verifiable: requires manual review or acceptance`.
   An item whose work has not been done is unfinished, not unverifiable: go back and do the work. "Deferred", "after merge", and "follow-up" are unfinished. The one place post-merge work lives is a `## On close` heading. Where the repo ships `scripts/ticket_check.sh`, `done` skips that heading and `close-ready` requires it ticked before `gh issue close`; without the script, tick it by hand before closing. An item that sits in `## Checklist` and can only happen after the merge is a ticket defect: leave it unticked, report it, and do not tick it early to reach `done`.
5. After all verifiable items are checked, update that ticket's `## Status` field to `done` — replace the whole body under that heading, not just insert a `done` line above the old text, or the section ends up self-contradicting (e.g. `done` followed by a stale `blocked` line). The ticket is `done` only when every item is checked or marked not verifiable.
6. If that ticket carries a `**Spec**:` field whose slug resolves to `.scratch/<slug>/spec.md`, and that spec has no other open sibling ticket, update the spec's inline `Status:` field to `done` too. A spec with open sibling tickets stays at its current status — one slice finishing does not close the spec.

Only once every completed ticket's checklist is verified and its Status is `done` does this phase end — that is the signal to commit, not code-review's report. Confirm by re-reading the written ticket: any remaining `- [ ]`, or a Status other than `done`, means the phase is not over.

When committing, stage each file by name (`git add <path>…`, never `git add -A`) and read `git diff --cached --name-only` before the commit; include any `Requirements:` field or inline `(ID)` tags from the ticket or spec in the commit message body and PR description so the trace survives into VCS history. Every test count, test name and pass figure in the commit message and PR body comes from your own test-runner output or a grep of the diff, never from the review report; name the scope as the testing skill words it ("N covering tests").

**Commit-only brief**: when the brief that started this run says commit-only (the `implement-spec` orchestrator sends it), the Test, Review and Checklist steps run as written. After the commit, skip the push, the PR, and the proof commands, and report the branch and the commit hash. The orchestrator created your worktree on the integration branch: work there and skip the branch switch and worktree entry above.

After the commit, push the feature branch and open the PR without asking; write the PR body with `Skill("pr")`; merging stays the user's. A GitHub-issue ticket is closed (`gh issue close <n>`) only after its commits are merged to the default branch; until then it stays open and the final report says the push or merge is pending.

Run each push, merge and close as its own Bash call: one denied step cancels a chained command, and the silence reads as success. Report a push, PR or merge as done only after quoting its proof: `git ls-remote --heads origin <branch>` for a push, the URL `gh pr create` printed, `gh pr view <n> --json state,mergedAt` for a merge.

A merge belongs in a PR from the feature branch: `gh pr create` needs no checkout of the default branch. When handing the user git commands for the main checkout, first read its branch from `git worktree list`, since other sessions leave it on feature branches.
