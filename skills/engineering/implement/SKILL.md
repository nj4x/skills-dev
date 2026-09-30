---
name: implement
description: "Implement a piece of work based on a spec or set of tickets. Use when the user says 'implement this', 'build this', or wants a ticket or spec worked through to a tested, reviewed state."
---

Fixed order, no step skipped or reordered: implement → test → review → checklist → commit. Reaching "ready to commit" without having run the checklist step is a process error, not a shortcut — go back and run it.

Use /tdd at every seam the ticket or spec names explicitly (look for a "Test seams" or "Acceptance criteria" section).

After each substantive change, run typechecking and the test file(s) that cover that change via `Skill("testing", args="--files <changed paths>")` — selective runner maps changed source files to covering tests, falls back to full suite only for uncovered files.

Once done, invoke the `code-review` skill via `Skill("code-review")` — not via the Agent tool's `subagent_type` parameter. Code-review's build gate runs the full suite as a mandatory guard.

## Ticket location

Resolve where each ticket's checklist and Status field live before the checklist workflow, and use that same location for every edit in that workflow:

- **Ticket is a repo file** (e.g. `.scratch/<slug>/draft-issues/*.md`): edit the file directly.
- **Ticket is a GitHub issue** (see the project's `docs/agents/issue-tracker.md` if present): `gh issue view <n> --json body -q .body` to read it, edit the body text, `gh issue edit <n> --body-file <tmp>` to write it back. Closing the issue (`gh issue close <n>`) is a separate, later action — see that doc for when it applies; it is not part of this checklist workflow.

## Verify-then-check checklist workflow

This phase runs after code-review produces zero Major or Critical findings, and before any commit. If findings remain, fix them first and re-run the review before proceeding.

For each ticket completed in this implementation effort:

1. Extract all `- [ ]` checklist items from the ticket (see Ticket location above).
2. For each unchecked item, **verify** that the work is done:
   - Run named test(s) if the item identifies test IDs.
   - Inspect code if the item describes behavior but no named test exists.
   - Check output, logs, or observable state if the item is output-observable.
   - Record the verification method as a brief note (e.g., `test SAB-GRP-FR-2.0.1-P-001 passed`, `code: see ClassName.method`).
3. If verification succeeds: rewrite the item as `- [x] <original text> — <verification note>`.
4. If an item cannot be verified (no test, no inspectable code, no observable output): do **not** check it. Append an inline comment: `— Item not verifiable: requires manual review or acceptance`.
5. After all verifiable items are checked, update that ticket's `## Status` field to `done`.
6. If that ticket carries a `**Spec**:` field whose slug resolves to `.scratch/<slug>/spec.md`, and that spec has no other open sibling ticket, update the spec's inline `Status:` field to `done` too. A spec with open sibling tickets stays at its current status — one slice finishing does not close the spec.

Only once every completed ticket's checklist is verified and its Status is `done` does this phase end — that is the signal to commit, not code-review's report.

When committing, include any `Requirements:` field or inline `(ID)` tags from the ticket or spec in the commit message body and PR description so the trace survives into VCS history.
