---
name: implement-spec
description: "Implement a specification in code."
disable-model-invocation: true
---

You have been provided a spec. This spec should have tickets associated with it, describing how to implement the spec.

The goal is a PR which implements the entire spec on a single branch.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

**Implementer subagents** should be run in the background where possible for **maximum concurrency**.

## Preconditions

Both a published spec and a published task graph must exist. If either is missing, stop and tell the user to run `/to-spec` and then `/to-tickets` first.

Where to find them depends on the tracker set up by `/setup-skills` (see `docs/agents/issue-tracker.md`):

- **Local tracker:** spec at `.scratch/<feature-slug>/spec.md`; tickets at `.scratch/<feature-slug>/issues/*.md`, each carrying a `Blocked by` field that encodes the task graph.
- **Real tracker (GitHub, Linear, …):** spec is a published issue; tickets are issues linked to it and to each other via the tracker's native blocking-issue relationships.

A `draft-issues/` or `draft-spec.md` staging directory with no matching `issues/`/`spec.md` means `to-tickets`/`to-spec` has not been approved and published yet — this is not a task graph to implement against.

## Steps

1. Read the spec and tickets. Read enough to understand the task graph.

2. (optional) Use an **exploration subagent** to conduct any exploration required by the tickets - relevant codebase files or external documentation. Ensure the exploration subagent can save files - it should save its markdown notes in a directory outside the repo, accessible by all future subagents. This lets **implementer subagents** focus on implementation rather than exploration.

3. Create a branch, and a draft PR. The PR should be marked as 'closing' the spec issue and tickets.

4. Use **implementer subagents** to implement each ticket. Each implementer subagent should work in its own worktree, on its own branch.

5. Once an **implementer subagent** completes, merge its work to the PR branch with a **merger subagent**.

6. If this changes the **frontier** of available tickets, kick off more **implementer subagents** to work on the new tickets. This allows for maximum concurrency.

7. Once all tickets are complete, run /code-review on the PR branch. Fix all issues raised by the code review in a single **implementer subagent**.

8. Mark the PR as ready for review.

9. Clean up all **implementer subagent** worktrees.
