---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, invoke the `code-review` skill (via the Skill tool) to review the work. Do NOT use the Agent tool with subagent_type to do this — use `Skill("code-review")` directly. After review is complete and all Major/Critical findings are fixed, update the issue/spec statuses:

- For each completed issue/ticket in `.scratch/`, update `Status:` from `ready-for-agent` to `done`.
- Update the spec's `Status:` from `ready-for-agent` to `done` (only after all acceptance criteria are verified).

Commit your work to the current branch. If the ticket or spec carries a `Requirements:` field or inline `(ID)` tags, include those requirement IDs in the commit message body (and the PR description, if you open one) so the trace survives into the VCS history.
