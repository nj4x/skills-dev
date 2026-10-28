---
lineage-rules: exempt
---

# ADR-0081: pr-worktree skill moves the session onto an existing PR branch

**Status**: Accepted  
**Date:** 2026-10-28  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet, retrofit tracked in ADR-0065)

## Context

Claude Desktop cuts each new session's worktree from `origin/main` on an app-named branch `ccdtp/<slug>-<hash>`. A session meant for an existing PR branch therefore starts on an empty branch off main. In the session "SAFB-4778 add/remove member worktree" the user asked to fetch `task/SAFB-4778-add-remove-member-tc` into a new worktree. The agent ran `git worktree add` but never called `EnterWorktree`. The shell reset its working directory to the session worktree after every Bash call, so each later command needed `cd <absolute path>`, and a missed `cd` would have run on main.

The New-session picker and `start_session source_branch` accept only an existing local branch, and they still cut a new `ccdtp/*` branch from it. A push from that branch does not reach the PR branch.

## Decision

1. **New model-invoked skill `skills/dev/pr-worktree`.** Model-invoked, not user-invoked: the failure began as a plain-words request, which a user-invoked skill cannot catch. Input is a branch name or a PR number. A PR number resolves through `gh pr view <n> --json headRefName,isCrossRepository`, run in the repo so the repo's own GitHub host applies. A fork PR (`isCrossRepository: true`) is out of scope: its branch is not on `origin`, so the skill stops with "fork PRs are not supported". A PR number that does not resolve also stops the skill.
2. **The worktree is on the real PR branch, with upstream set.** Path: `<main working tree>/.claude/worktrees/<branch with "/" replaced by "-">`. The full branch name avoids collisions between prefixes such as `task/x` and `bugfix/x`. Every row that ends on a worktree sets `git branch --set-upstream-to=origin/<branch> <branch>` when the branch has no upstream. The skill ends with `EnterWorktree` (path), so every later command runs in that worktree.
3. **Fetch first.** Before the table, run `git fetch origin <branch>`. When `origin/<branch>` does not exist after the fetch, stop and report; the skill never creates a branch that is not on `origin`. Every row and step 5 compare against this fresh ref.
4. **Where the branch already is decides the path:**

   | Branch state | Action |
   |---|---|
   | Not checked out anywhere | `git worktree add` (with `--track -b` when no local branch exists), then step 5. |
   | Checked out in a worktree under `.claude/worktrees/` | Step 5 in that worktree, then `EnterWorktree` that path. |
   | Checked out in the main working tree, tree clean | Check divergence first: when the local branch and `origin/<branch>` have diverged, stop before asking. Otherwise ask once. On yes: `git -C <main> branch -m <branch> <branch>-local`, `git branch --unset-upstream <branch>-local`, `git worktree add -b <branch> <path> <branch>-local`, then step 5. |
   | Checked out in the main working tree, tree dirty | Stop and report the path. |
   | Checked out in another linked worktree, outside `.claude/worktrees/` (made by hand, or left by an earlier session) | Stop and report that path. The skill does not rename or move a branch in a worktree it did not make. |

5. **Remote sync rule**, run in the target worktree. Local branch behind `origin/<branch>`: `git merge --ff-only`, but only when the worktree is clean; with uncommitted changes, skip the pull and report the file count. Diverged: stop and report, without `EnterWorktree`. The skill never resets a branch.

## Considered Options

- **Memory note** instead of a skill: rejected. A note depends on recall triggering; a skill runs the same steps every time.
- **Desktop picker / `start_session source_branch`**: rejected. Both leave the session on a `ccdtp/*` branch with no upstream to the PR branch.
- **Detach HEAD in the main working tree** (`git switch --detach`) to free the branch: rejected by the user. A detached HEAD invites commits that belong to no branch. Renaming keeps a named branch in the main working tree.
- **Switch the main working tree to `main`**: rejected. It rewrites files under an open IDE or a running build.
- **Stop and report on a clean main working tree too**: rejected. The user would rename the branch by hand every time; the rename is safe on a clean tree after one confirmation.
- **Fork PRs through the head repository's remote**: out of scope. It needs a second remote per fork.

## Consequences

- The rename leaves a `<branch>-local` branch in the main working tree for the user to delete later. The rename copies the upstream config, so the skill removes it: with no upstream, no `push.default` setting can send `<branch>-local` to the PR branch.
- The new branch starts from the renamed branch's tip, not from `origin`, so unpushed local commits carry over.
- `EnterWorktree` accepts only paths under `.claude/worktrees/` from a session already in a worktree; this is why the main-working-tree rows exist. A branch in another linked worktree outside `.claude/worktrees/` needs the user: git refuses a second checkout, and the skill cannot enter that path. The user removes that worktree (`git worktree remove`) or moves the branch, then runs the skill again.
