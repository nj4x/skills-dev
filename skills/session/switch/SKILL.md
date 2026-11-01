---
name: switch
description: Switch to the default branch (or a named one), fetch, and fast-forward it before starting a task.
argument-hint: "[branch]"
disable-model-invocation: true
---

# switch

Put the working tree on a branch that matches `origin`, so a new task starts from current code. The branch is the argument, else the repo's default branch.

A **stop** ends the skill: print the reason and the state, change nothing more. Any failing git command is a stop.

## Steps

**1. Pick the branch `B`.** An argument is used as given, minus a leading `origin/`. Otherwise read the default from `origin`:

```bash
git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||'
```

When that fails, run `git remote set-head origin --auto` and read it again.

**2. Fetch.**

```bash
git fetch origin --prune
git rev-parse --verify --quiet "refs/remotes/origin/$B"
```

Stop when `origin/$B` does not exist.

**3. Check the tree is clean.** `git status --porcelain` empty. Stop otherwise and report the file count: switching would carry or lose those changes.

**4. Switch.** A **detach** is `git switch --detach "origin/$B"`; it ends the skill after step 6, skipping step 5, because a detached HEAD holds no branch.

- A linked worktree is one where `git rev-parse --git-dir` differs from `git rev-parse --git-common-dir`. With no argument there, detach: taking the default branch would block `git checkout $B` in the main checkout.
- Otherwise `git switch "$B"`. With no local `$B`, `git switch --track -b "$B" "origin/$B"`.
- When another worktree holds `$B`, detach and report that worktree's path.

**5. Pull.** Read `git rev-list --left-right --count "$B...origin/$B"` as `<ahead> <behind>`. Both > 0: stop and report both. Otherwise `git merge --ff-only "origin/$B"`.

**6. Report.** One line: `B`, short HEAD sha, `<behind>` as commits pulled, `<ahead>` as unpushed commits when > 0. After a detach: `detached at origin/$B`, short sha, and the reason (linked worktree, or the holding worktree's path).
