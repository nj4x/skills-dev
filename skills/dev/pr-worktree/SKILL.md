---
name: pr-worktree
description: Move the session into a worktree on an existing PR or remote branch. Use when the user names a PR number or existing branch to work on, or asks to fetch a branch into a worktree.
argument-hint: "<branch | PR number>"
---

# pr-worktree

A Claude Desktop session starts on an app-named `ccdtp/*` branch cut from `origin/main`. This skill puts the session on the **real PR branch**, with its upstream set, in a worktree under `<main working tree>/.claude/worktrees/`, and ends with `EnterWorktree` so every later command runs there.

Run every git command from the session's current directory: all worktrees share one repository. Touch the main working tree only through `git -C "$MAIN"` in step 5.

A **stop** ends the skill: print the reason and the state, change nothing more, and do not call `EnterWorktree`. Any failing git command is a stop, except the probes (`show-ref`, `rev-parse`) whose exit code chooses the next action.

## Steps

**1. Load the tool.** `EnterWorktree` is deferred: load it with ToolSearch `select:EnterWorktree`.

**2. Resolve the branch.** A branch name is used as given, minus a leading `origin/`. A PR number:

```bash
gh pr view <n> --json headRefName,isCrossRepository
```

Run it in the repo, so the repo's own GitHub host applies. Stop when the PR does not resolve. Stop with "fork PRs are not supported" when `isCrossRepository` is `true`: a fork's branch is not on `origin`. Store the branch as `B`.

**3. Locate the repo and fetch.**

```bash
MAIN=$(git worktree list --porcelain | awk 'NR==1{print substr($0,10); exit}')
WT="$MAIN/.claude/worktrees/$(printf '%s' "$B" | tr '/' '-')"
git fetch origin "$B"
git rev-parse --verify --quiet "refs/remotes/origin/$B"
```

Stop when `origin/$B` does not exist after the fetch. Every later comparison uses this fresh ref.

**4. Find where `B` is checked out** (`HOLDER`, empty when none):

```bash
HOLDER=$(git worktree list --porcelain | awk -v b="refs/heads/$B" '/^worktree /{p=substr($0,10)} $0=="branch "b{print p}')
```

**5. Act on the branch state.** Exactly one row applies.

| Branch state | Action |
|---|---|
| `HOLDER` empty | `git show-ref --verify --quiet "refs/heads/$B"` — local branch exists: `git worktree add "$WT" "$B"`. No local branch: `git worktree add --track -b "$B" "$WT" "origin/$B"`. Then step 6 in `WT`. |
| `HOLDER` under `$MAIN/.claude/worktrees/` | `WT=$HOLDER`. Step 6 in `WT`. When `WT` is the current directory, skip step 7. |
| `HOLDER` = `MAIN`, `git -C "$MAIN" status --porcelain` empty | Run step 6's `rev-list --left-right --count "$B...origin/$B"`; when both counts are > 0, stop before asking. Otherwise ask once: "Rename `B` to `B-local` in `MAIN` to free it for a worktree? (yes/no)". On no, stop. On yes, run the three commands below, then step 6 in `WT`. |
| `HOLDER` = `MAIN`, uncommitted changes | Stop. Report `MAIN` and the file count: someone is working on `B` there. |
| `HOLDER` is any other path | Stop. Report `HOLDER`: the skill changes no branch in a worktree it did not make. The user runs `git worktree remove <HOLDER>` or switches that worktree off `B`, then runs the skill again. |

Rename commands (main working tree, clean):

```bash
git -C "$MAIN" branch -m "$B" "$B-local"
git branch --unset-upstream "$B-local"
git worktree add -b "$B" "$WT" "$B-local"
```

The new branch starts from the renamed tip, so unpushed local commits carry over. With its upstream removed, `B-local` cannot push to the PR branch under any `push.default`.

**6. Sync with the remote**, in `WT`.

```bash
git -C "$WT" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null \
  || git -C "$WT" branch --set-upstream-to="origin/$B" "$B"
git -C "$WT" rev-list --left-right --count "$B...origin/$B"   # prints: <ahead> <behind>
```

- **Up to date or only ahead**: nothing to pull.
- **Behind only**: when `git -C "$WT" status --porcelain` is empty, `git -C "$WT" merge --ff-only "origin/$B"`. With uncommitted changes, skip the pull and report "N uncommitted files; not pulled".
- **Diverged** (both counts > 0): stop and report both counts.

**7. Enter the worktree.** Call `EnterWorktree` with `path: WT`.

**8. Report.** One block: `WT`, `B`, its upstream, ahead/behind after the sync, and — after a rename — the `B-local` branch left in `MAIN` for the user to delete.
