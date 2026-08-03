---
name: implement
description: "Implement a piece of work based on a spec or set of tickets. Use when the user says 'implement this', 'build this', or wants a ticket or spec worked through to a tested, reviewed state."
---

Use /tdd at every seam the ticket or spec names explicitly (look for a "Test seams" or "Acceptance criteria" section).

After each substantive change, run typechecking and the test file(s) that cover that change. Run the full test suite once before invoking code-review.

Once done, invoke the `code-review` skill via `Skill("code-review")` — not via the Agent tool's `subagent_type` parameter.

## Verify-then-check checklist workflow

This phase runs **only after code-review produces zero Major or Critical findings**. If any remain, fix them first and re-run the review before proceeding.

For each ticket completed in this implementation effort:

1. Extract all `- [ ]` checklist items from the ticket file.
2. For each unchecked item, **verify** that the work is done:
   - Run named test(s) if the item identifies test IDs.
   - Inspect code if the item describes behavior but no named test exists.
   - Check output, logs, or observable state if the item is output-observable.
   - Record the verification method as a brief note (e.g., `test SAB-GRP-FR-2.0.1-P-001 passed`, `code: see ClassName.method`).
3. If verification succeeds: rewrite the item as `- [x] <original text> — <verification note>`.
4. If an item cannot be verified (no test, no inspectable code, no observable output): do **not** check it. Append an inline comment: `— Item not verifiable: requires manual review or acceptance`.
5. After all verifiable items are checked, update that ticket's `## Status` field to `done`.
6. If that ticket carries a `**Spec**:` field whose slug resolves to `.scratch/<slug>/spec.md`, update that spec's inline `Status:` field to `done` as well (once all verifiable items are checked — the same threshold as step 5).

When committing, include any `Requirements:` field or inline `(ID)` tags from the ticket or spec in the commit message body and PR description so the trace survives into VCS history.
