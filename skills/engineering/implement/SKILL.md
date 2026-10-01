---
name: implement
description: "Implement a piece of work based on a spec or set of tickets. Use when the user says 'implement this', 'build this', or wants a ticket or spec worked through to a tested, reviewed state."
---

Fixed order, no step skipped or reordered: implement → test → review → checklist → commit. Reaching "ready to commit" without having run the checklist step is a process error, not a shortcut — go back and run it.

Before writing any code, use TaskCreate to add one task per remaining step — Test, Review, Checklist, Commit — and chain them with `addBlockedBy` (Commit blockedBy Checklist, Checklist blockedBy Review, Review blockedBy Test). This makes the order a property of the task graph, not just this paragraph: git commit only once TaskList shows Commit unblocked. A follow-up fix discovered after Review or Checklist already completed (e.g. a bug found post-hoc) re-enters at Test — create a fresh Test/Review/Checklist/Commit chain for it; do not reuse or bypass the completed one.

Use /tdd at every seam the ticket or spec names explicitly (look for a "Test seams" or "Acceptance criteria" section).

Before designing, check the ticket's stated root cause or premise against the code. When the code contradicts the ticket, record the mismatch in the checklist note and the commit message body, and write the commit message from what the code shows.

After each substantive change, run typechecking and the test file(s) that cover that change via `Skill("testing", args="--files <changed paths>")` — selective runner maps changed source files to covering tests, falls back to full suite only for uncovered files.

Once done, run review in a fresh session that inherits none of this session's context: `Agent({subagent_type: "general-purpose", ...})` — never `"fork"` (a fork inherits this session's context and can skip the fan-out, reasoning from memory instead of actually reading the diff) and never an inline `Skill("code-review")` call in this session (same problem: it reasons from what it already wrote, not from a fresh read). Brief the fresh agent with the ticket number, the diff scope (committed/working-tree), the effort level, and `--build-cmd "<lint command> && <the exact test command the Test step ran>"`, and instruct it to call `Skill("code-review", args="--build-cmd ...")` itself and return the structured report. The Test step already chose the covering tests, so the build gate re-runs that set, not the whole suite. Code-review's build gate is a mandatory guard.

A diff that touches only docstrings, comments, message strings, and docs is a **light review**: brief the agent with effort `low`, hand it the diff, and have it verify each factual claim in the changed text against the code it names. The fresh session, `Skill("code-review")` call, and build gate are unchanged.

Review is complete only when the agent's completion notification delivers its report with the build gate resolved (green or red, never in progress). Until then the Review task stays `in_progress`, Commit stays blocked, and the report's text comes from that notification alone — keep working on read-only steps (checklist verification) while it runs.

A ticket that changes no code (a lineage ticket: ADRs, requirements, docs) still runs every step. Its Test step is lint only (the testing skill's docs-only rule), and code-review runs in its docs-only mode. The ticket's checklist still governs what "done" means — authoring the ADR is not done when the checklist also asks for FS merges or ticket-body updates.

## Ticket location

Resolve where each ticket's checklist and Status field live before the checklist workflow, and use that same location for every edit in that workflow:

- **Ticket is a repo file** (e.g. `.scratch/<slug>/draft-issues/*.md`): edit the file directly.
- **Ticket is a GitHub issue** (see the project's `docs/agents/issue-tracker.md` if present): `gh issue view <n> --json body -q .body` to read it, edit the body text, `gh issue edit <n> --body-file <tmp>` to write it back. Closing the issue (`gh issue close <n>`) is a separate, later action — see that doc for when it applies; it is not part of this checklist workflow.

## Verify-then-check checklist workflow

This phase runs after code-review produces zero Major or Critical findings, and before any commit. If findings remain, fix them first and re-run the review before proceeding. The Review task is done only when the **latest** report — on the diff as it stands after your fixes — has zero Major/Critical; fixing findings and moving on without a fresh report against the final diff is the same process error as skipping Review outright. Set the Review task back to `in_progress` the moment a fix changes the diff, even a fix for a single Minor finding, and dispatch another fresh-session review (same rules as the first) before re-completing it. Triage each Minor finding before the checklist: fix it (and re-review) or list it under "left as is" in the final report.

For each ticket completed in this implementation effort:

1. Extract all `- [ ]` checklist items from the ticket (see Ticket location above).
2. For each unchecked item, **verify** that the work is done:
   - Run named test(s) if the item identifies test IDs.
   - Inspect code if the item describes behavior but no named test exists.
   - Check output, logs, or observable state if the item is output-observable.
   - Record the verification method as a brief note (e.g., `test SAB-GRP-FR-2.0.1-P-001 passed`, `code: see ClassName.method`).
3. If verification succeeds: rewrite the item as `- [x] <original text> — <verification note>`. Keep every item and its original text verbatim; an item for a branch not taken (e.g. "If fix: …" when the decision was document-only) becomes `- [x] <original text> — n/a: <branch chosen>`, never merged or dropped. Name code in notes by symbol (`run_root_cause_pass`), never `file:line`; line numbers shift with the same diff and rot afterward. Re-grep every symbol or path you cite in the note and the commit message against the final diff before writing it.
4. If an item cannot be verified (no test, no inspectable code, no observable output): do **not** check it. Append an inline comment: `— Item not verifiable: requires manual review or acceptance`.
   An item whose work has not been done is unfinished, not unverifiable: go back and do the work. "Deferred", "after merge", and "follow-up" are unfinished.
5. After all verifiable items are checked, update that ticket's `## Status` field to `done` — replace the whole body under that heading, not just insert a `done` line above the old text, or the section ends up self-contradicting (e.g. `done` followed by a stale `blocked` line). The ticket is `done` only when every item is checked or marked not verifiable.
6. If that ticket carries a `**Spec**:` field whose slug resolves to `.scratch/<slug>/spec.md`, and that spec has no other open sibling ticket, update the spec's inline `Status:` field to `done` too. A spec with open sibling tickets stays at its current status — one slice finishing does not close the spec.

Only once every completed ticket's checklist is verified and its Status is `done` does this phase end — that is the signal to commit, not code-review's report.

When committing, include any `Requirements:` field or inline `(ID)` tags from the ticket or spec in the commit message body and PR description so the trace survives into VCS history.

After the commit, ask the user before pushing. A GitHub-issue ticket is closed (`gh issue close <n>`) only after its commits are pushed; until then it stays open and the final report says the push is pending.
