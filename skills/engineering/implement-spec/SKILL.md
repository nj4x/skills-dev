---
name: implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
disable-model-invocation: true
---

You have been provided a spec. This spec should have tickets associated with it, describing how to implement the spec.

The goal is the entire spec implemented on a single **integration branch**, with every ticket resolved the way the issue tracker closes work.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

**Implementer subagents** should be run in the background where possible for **maximum concurrency** — when this skill runs in the main conversation. Launch independent implementers in a single message. When this skill itself runs as a subagent, launch them in the foreground instead (single message, results return inline): `notify_when_idle` and background-completion waits are main-conversation-only.

## Preconditions

Both a published spec and a published task graph must exist. If either is missing, stop and tell the user to run `/to-spec` and then `/to-tickets` first.

Where to find them depends on the tracker set up by `/setup-skills` (see `docs/agents/issue-tracker.md`):

- **Local tracker:** spec at `.scratch/<feature-slug>/spec.md`; tickets at `.scratch/<feature-slug>/issues/*.md`, each carrying a `Blocked by` field that encodes the task graph.
- **Real tracker (GitHub, Linear, …):** spec is a published issue; tickets are issues linked to it and to each other via the tracker's native blocking-issue relationships.

A `draft-issues/` or `draft-spec.md` staging directory with no matching `issues/`/`spec.md` means `to-tickets`/`to-spec` has not been approved and published yet — this is not a task graph to implement against.

## Steps

1. Read the spec and tickets to understand the task graph.

2. (optional) Use an **exploration subagent** to conduct any exploration required by the tickets - relevant codebase files or external documentation. Ensure the exploration subagent can save files - it should save its markdown notes in a directory outside the repo, accessible by all future subagents. This lets **implementer subagents** focus on implementation rather than exploration.

3. Create the integration branch. If the issue tracker closes work through PRs, or the user asks for one, open a draft PR after the first merge in step 5 (a branch with no commits ahead of main can't open one), marked as closing the spec and tickets.

4. Use **implementer subagents** to implement each ticket, each in its own worktree on its own branch. Each implementer subagent:
   - confirms its worktree is based on the integration branch before starting, and resets onto it if not;
   - calls the Skill tool with `tdd` to build the ticket;
   - merges the integration branch tip into its own branch before reporting done

5. Once an **implementer subagent** completes, merge its work to the integration branch with a **merger subagent**.

6. If this changes the **frontier** of available tickets, kick off more **implementer subagents** to work on the new tickets. This allows for maximum concurrency.

7. Once all tickets are complete, call the Skill tool with `code-review` on the integration branch. Fix all issues raised by the code review in a single **implementer subagent**.

8. If a draft PR exists, mark it ready for review. Otherwise, resolve each ticket the way the issue tracker closes work, and report the integration branch.

9. Clean up all **implementer subagent** worktrees.
