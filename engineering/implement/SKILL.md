---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, spawn a subagent (via the Agent tool) and invoke /code-review inside it to review the work in an isolated context. After review is complete and all Major/Critical findings are fixed, update the issue/spec statuses:

- For each completed issue/ticket in `.scratch/`, update `Status:` from `ready-for-agent` to `done`.
- Update the spec's `Status:` from `ready-for-agent` to `done` (only after all acceptance criteria are verified).

Commit your work to the current branch. If the ticket or spec carries a `Requirements:` field or inline `(ID)` tags, include those requirement IDs in the commit message body (and the PR description, if you open one) so the trace survives into the VCS history.
