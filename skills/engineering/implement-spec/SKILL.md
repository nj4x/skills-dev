---
name: implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
disable-model-invocation: true
---

You have been provided a spec. This spec should have tickets associated with it, describing how to implement the spec.

The goal is the entire spec implemented on a single **integration branch**, with every ticket resolved the way the issue tracker closes work.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them. This means there is always a **frontier** of tickets which are ready to be grabbed.

Communication to and from subagents should be sparse. Communicate primarily through **context pointers**: to the spec, tickets, research notes, and previous commits. Don't duplicate information already available via pointers.

**Implementer subagents** should be run in the background where possible for **maximum concurrency**. Launch independent implementers in a single message.

## Where this skill runs

Run this skill in the main conversation only. Each implementer calls `implement`, which dispatches its own fresh reviewer, and that reviewer's `code-review` dispatches finders. A probe in this harness showed that a subagent at level 3 has no Agent tool (the main session is level 0), so a reviewer under a subagent-run `implement-spec` could not start. When you were started through the Agent tool rather than by the user's own `/implement-spec`, stop and tell the caller to run `/implement-spec` in the main conversation.

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

4. Read the spec and each ticket, and list the test seams of each ticket. Use **implementer subagents** to implement each ticket, each in its own worktree on its own branch. Each implementer subagent:
   - confirms its worktree is based on the integration branch before starting, and resets onto it if not;
   - calls the Skill tool with `implement` to build the ticket. The brief says **commit-only**: the Test, Review and Checklist steps run as written, then it commits on the worktree branch with no push and no PR. The brief carries the ticket's `Test seams:` list. `implement` ticks the ticket's checklist and sets its `## Status` to `done` after its review gates hold; it skips the checklist step that sets the spec's inline `Status`, which only you set;
   - merges the integration branch tip into its own branch before reporting done;
   - ends with a final result that names the branch, the commit hash, and one `<seam>: <test id or path>` line per listed seam (`<seam>: none — <reason>` when no test covers it).

   A **blocked ticket** is any dispatched ticket that returns without a commit, for any reason: the round limit, the Test limit (see `implement`, **Round limit and stop**), or a subagent failure. A blocked implementer returns a stop report: the open findings or failing test summary, its branch, its worktree path, and the tickets it blocks. When a subagent returns no stop report, write one.

5. Once an **implementer subagent** completes with a commit, merge its work to the integration branch with a **merger subagent**. Do not merge a blocked ticket. A committed branch that conflicts on merge counts as blocked: its GitHub issue already shows `done`; do not revert it, and note that in the report.

6. If this changes the **frontier** of available tickets, kick off more **implementer subagents** to work on the new tickets. This allows for maximum concurrency. Do not dispatch a ticket that depends, directly or transitively, on a blocked ticket; it stays unresolved. Independent tickets continue.

7. Once every dispatched ticket has merged or is blocked, review the integration branch. When no ticket merged, skip this step. Otherwise:
   - **Test gate:** run `Skill("testing", args="--files <every path changed on the integration branch since its base>")` on the integration tip and quote the green summary line. When tests fail, send the failures to the **integration fixer**; this does not count as a round. Allow 3 fix passes per Test gate without a green line; at the limit, stop (step 8).
   - **Reviewer:** dispatch a fresh `general-purpose` agent, never `"fork"` and never an inline `Skill("code-review")`. Render its prompt with `python3 ~/.claude/skills/implement/render_review_brief.py --spec <spec> --ticket <merged ticket> [--ticket …] --worktree <abs path> --branch <integration branch> --scope committed --effort high --git "<git binary>" --build-cmd "<lint> && <type-check>" --test-evidence "<green summary line>" --check "<question>" [--check …]` and pass its stdout verbatim. Pass only merged tickets. Write one `--check` per `<seam>: <test>` pair: "Is the reported covering test for <seam> in the diff, and does it exercise the seam?" A `none` entry is a Major finding unless the implementer's reason holds. Add cross-ticket questions, such as whether two tickets use the same interface. Every integration review is a full review at `--effort high`; use no light or delta review. A re-review reruns the script with `--diff-changed`.
   - **Gates:** hold the four gates under **Review is complete** in `~/.claude/skills/implement/SKILL.md` (hand-back frame, completion notification, no review agent still running, quoted `Verdict:` line), and re-review on any diff change. The review ends only when the latest report has zero Critical and zero Major.
   - **Integration fixer:** one implementer subagent in its own worktree on the integration tip fixes the Critical and Major findings with plain edits. It does not call `Skill("implement")`. It triages each finding against the code as `implement` requires, and fixes Minor findings in the same pass or lists them "left as is". It runs `Skill("testing", args="--files <changed paths>")`, quotes the green summary line, commits on its branch with no push and no PR, and a merger subagent merges it. The next review brief carries that fresh green line.
   - **Rounds:** this loop has its own counter. A round is one review whose report has Critical or Major above zero, or one re-review run after a Minor-only fix. Allow at most 3 rounds. After the third round ends, run no fix pass. When its report has zero Critical and zero Major, the review is complete: list the open Minor findings as "left as is". Otherwise stop (step 8).

8. Finish. The run is **partial** when a ticket is blocked or undispatched, or when no ticket merged. An integration stop (the round limit or the Test limit reached) also ends the run unresolved.
   - Partial or stopped: do not set the spec's inline `Status` to `done`, and do not mark a draft PR ready. Report to the user: the integration branch, every blocked ticket with its open findings or failing test summary and its worktree path, every undispatched ticket with the ticket that blocks it, the open integration findings or the failing integration Test summary, each merged `done` ticket that has open integration findings, the integration fixer's worktree path, and any GitHub issue that shows `done` for a ticket that did not merge. With a local tracker and no PR, blocked and dependent tickets keep their current `Status`. With a GitHub tracker and no PR, the issues stay open; closing waits until the commits reach the default branch, which the user does.
   - Otherwise: set the spec's inline `Status` to `done`, once. If a draft PR exists, mark it ready for review. Otherwise, resolve each ticket the way the issue tracker closes work, and report the integration branch.

9. Clean up all **implementer subagent** worktrees, except the worktree of each blocked ticket and, after an integration stop, the integration fixer's worktree: keep them for inspection.
