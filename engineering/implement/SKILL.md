---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, invoke the `code-review` skill (via the Skill tool) to review the work. Do NOT use the Agent tool with subagent_type to do this — use `Skill("code-review")` directly.

## Verify-then-check checklist workflow (ADR-0062)

This phase runs **only after code-review produces zero Major or Critical findings**. If any remain, fix them first and re-run the review before proceeding.

1. Extract all `- [ ]` checklist items from the ticket file.
2. For each unchecked item, **verify** that the work is done:
   - Run the relevant test(s) if the item names test IDs or describes testable behavior.
   - Inspect code to confirm the behavior is present if the item is behavioral.
   - Check output, logs, or observable state if the item is output-observable.
   - Record the verification method as a brief note (e.g., `test SAB-GRP-FR-2.0.1-P-001 passed`, `code: see ClassName.method`).
3. If verification succeeds: rewrite the item as `- [x] <original text> — <verification note>`.
4. If an item cannot be verified (no test, no inspectable code, no observable output): do **not** check it. Append an inline comment: `— Item not verifiable: requires manual review or acceptance`.
5. After all verifiable items are checked, update the ticket's `## Status` field to `done`.
6. If the ticket carries a `**Spec**:` field pointing to `.scratch/<slug>/spec.md`, update that spec's `## Status` field to `done` as well (only after all acceptance criteria are verified).

Commit your work to the current branch. If the ticket or spec carries a `Requirements:` field or inline `(ID)` tags, include those requirement IDs in the commit message body (and the PR description, if you open one) so the trace survives into the VCS history.
