---
lineage-rules: exempt
---

# ADR-0082: code-review stops early on a branch with zero commits ahead of the review base

**Status**: Accepted  
**Date:** 2026-10-28  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet, retrofit tracked in ADR-0065)

## Context

`/code-review --scope committed` Step 1 stops only on `main`. A Claude Desktop session sits on an app-named `ccdtp/*` branch cut from `origin/main`, so it can have zero commits of its own. Such a review failed only at Step 3 ("No committed changes"), after the Step 2 build gate (about 2 minutes for `./gradlew clean build openapi3`). In the session "SAFB-4778 add/remove member worktree" the agent caught this only by running `git log origin/main..HEAD` by hand, in the wrong worktree.

## Decision

1. **Guard placement.** Step 1, right after the fetch and the branch divergence gate, before Step 1.5 PR intake and the Step 2 build. This is the cheapest point where `origin/$REVIEW_BASE_REF` is fresh.
2. **Check.** `git rev-list --count origin/$REVIEW_BASE_REF..HEAD`. On `0`, stop and print each worktree from `git worktree list` with its branch and its commit count ahead of `origin/$REVIEW_BASE_REF`. The message labels the counts as relative to this review base, because another worktree's PR can target a different base. Suggest `/pr-worktree <branch>` (ADR-0081) or entering a listed worktree. The review never moves the session itself.
3. **Hard-stop rule exception.** The rule "no `git log origin/<base>..HEAD` before the build gate" bans reading the change before the gates. A commit count reads no change content, so the guard states that it is allowed.
4. **Coverage.** Committed scope in every `--mode`; mutating modes inherit it through Step 1. Working-tree scope has no Step 1 and stays unchanged.

## Considered Options

- **Warn and continue**: rejected. A review of zero commits has nothing to grade, so the run only wastes the build.
- **Check after the build** (the existing Step 3 "No committed changes"): rejected. It costs the full build gate, about 2 minutes, before the stop.
- **Wider "wrong branch" check** (for example a `ccdtp/*` branch with commits that is not the PR branch): out of scope. The guard covers only the zero-commit case.
