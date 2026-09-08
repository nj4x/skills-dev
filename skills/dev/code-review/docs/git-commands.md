# Git Commands Reference

This module contains essential Git commands for code review workflows. Resolve review scope before running any diff/stat/log command.

## Scope Precondition

- `committed` is the default review policy, but ambiguous or omitted scope requires a clarification question before review work.
- `working-tree` scope is selected only by explicit uncommitted/local-change wording or by user confirmation.
- Always validate git repository state and `HEAD` before diffing.

```bash
git rev-parse --is-inside-work-tree
git rev-parse --verify HEAD
```

## Gate-First Rule

These commands are for the change-analysis phase only.

Before committed-scope diff/stat/log commands, resolve:

1. Repository and branch checks.
2. Resolve `REVIEW_BASE_REF` (PR base branch, fallback `main`), then `git fetch origin "$REVIEW_BASE_REF"` and current branch fetch.
3. Branch divergence check.
4. PR context gate when `gh` is available, or explicit disabled reason.
5. Build/OpenAPI gate, or explicit waiver.

Before working-tree diff/stat commands, resolve:

1. Scope confirmation or explicit working-tree request.
2. Git repository and valid `HEAD` checks.
3. Build/OpenAPI gate, or explicit waiver.

Running diff/stat/log commands earlier is a workflow violation because it can omit PR feedback, review stale generated specs, or inspect the wrong scope.

## Committed Scope Commands

Committed scope reviews branch commits against the freshly fetched remote base. Resolve `REVIEW_BASE_REF` from the PR base branch (`baseRefName`, fallback `main`) and use `origin/$REVIEW_BASE_REF` (the discovered PR base), not local `main`.

### Fetch Baseline

```bash
REVIEW_BASE_REF=main   # replace with the resolved PR base branch (baseRefName); fallback main
git fetch origin "$REVIEW_BASE_REF"
CURRENT_BRANCH=$(git branch --show-current)
git fetch origin "$CURRENT_BRANCH"
git status
```

### Get Change Statistics

The committed-scope `diff` uses the three-dot `origin/$REVIEW_BASE_REF...HEAD` (merge-base) form so the counts match the GitHub PR Files-changed view. `git diff A...B` computes the merge-base of the local refs, so the result is only PR-accurate after the fetch above. The `git log` range stays two-dot (`..`).

```bash
git --no-pager diff --stat "origin/$REVIEW_BASE_REF...HEAD"
git --no-pager diff --shortstat "origin/$REVIEW_BASE_REF...HEAD"
git --no-pager diff --name-status "origin/$REVIEW_BASE_REF...HEAD"
git --no-pager diff --name-only "origin/$REVIEW_BASE_REF...HEAD"
```

### Get Full Diff

```bash
git --no-pager diff "origin/$REVIEW_BASE_REF...HEAD"
```

### Get Commit Log

```bash
git log "origin/$REVIEW_BASE_REF..HEAD" --pretty=format:"%h - %s"   # two-dot range: commits unique to HEAD
```

## Working-Tree Scope Commands

Working-tree scope reviews uncommitted local changes. It does not require fetch, branch divergence checks, PR gates, or committed branch comparison.

### Validate Repository

```bash
git rev-parse --is-inside-work-tree
git rev-parse --verify HEAD
```

### Get Change Statistics

```bash
git --no-pager diff --stat HEAD
git --no-pager diff --shortstat HEAD
git --no-pager diff --name-status HEAD
git --no-pager diff --name-only HEAD
```

### Get Full Diff

```bash
git --no-pager diff HEAD
```

Working-tree scope has no commit log requirement because changes are uncommitted.

## PR Context Commands

When committed scope has PR integration enabled, use helper-script intake for PR metadata and unresolved review threads:

```bash
python3 <skill dir>/scripts/code_review_pr_helper.py discover --output /tmp/code-review-pr-discover.json
python3 <skill dir>/scripts/code_review_pr_helper.py triage --discover-json /tmp/code-review-pr-discover.json --output /tmp/code-review-pr-triage.json
```

Optional PR UI corroboration, not a primary review baseline:

```bash
gh pr diff <PR_NUMBER> --name-only
gh pr diff <PR_NUMBER> --patch
```

Do not use PR comments as a substitute for unresolved review-thread intake.

## Autonomous Mutating-Mode Commands (`--mode autofix` / `review-to-merge`)

Reference for the commit and merge steps of workflow.md Step 14 (RTM-5 / RTM-7). These run **only** when `REVIEW_MODE_AUTONOMOUS = YES`, only after every read-only gate is green, and each is a BLOCKING consent gate — print the exact command and wait for explicit user confirmation before executing. Capture the pre-RTM HEAD anchor first so every recovery path has a rollback target.

```bash
PRE_RTM_SHA=$(git rev-parse HEAD)   # rollback anchor, captured at RTM-1
```

### Structured Autofix Commit (RTM-5)

Stage ALL changes (modified + renames + new files) — never a partial set — then commit with a structured message that lists each finding and its fix. Pass the message via a HEREDOC to preserve formatting.

```bash
git add -A   # or explicit paths covering every modified/renamed/new file from the fix set
git commit -m "$(cat <<'EOF'
fix(review): resolve <N> Major/Critical findings from autonomous review

- [CRITICAL] <file:line> — <finding> → <fix>; regression test: <test>
- [MAJOR]    <file:line> — <finding> → <fix>; regression test: <test>

Suite: <green summary>. Mode: autofix.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
NEW_SHA=$(git rev-parse HEAD)
```

`autofix` stops here; report `NEW_SHA`.

### Push + Safe Merge to Main (RTM-7, `review-to-merge` only)

Push the feature branch, then re-evaluate merge safety before merging. Each command is a separate BLOCKING gate.

```bash
CURRENT_BRANCH=$(git branch --show-current)
git push -u origin "$CURRENT_BRANCH"            # BLOCKING gate

# Merge-safety re-check before merging: re-fetch base, confirm not behind, no conflicts.
REVIEW_BASE_REF=main                            # resolved base; global convention merges into main
git fetch origin "$REVIEW_BASE_REF"
git --no-pager log --oneline "HEAD..origin/$REVIEW_BASE_REF"   # empty => branch not behind base
```

If a PR exists, prefer merging through it (`gh pr merge`); otherwise merge the working branch into main per the global "merge working branch into main" convention:

```bash
# Only after the merge-safety gate passes AND explicit merge consent:
git switch "$REVIEW_BASE_REF"
git merge --no-ff "$CURRENT_BRANCH"             # resolve conflicts as findings; never --force
```

If any safety condition fails (conflicts, branch behind base, protected branch, failing CI on main) → STOP after push, report what blocked the merge, do not force. Recovery anchors: `PRE_RTM_SHA` (pre-mutation), `NEW_SHA` (post-fix commit).

## Best Practices

- Always use `--no-pager` to avoid interactive pagers.
- Add `|| true` to grep commands that may find nothing.
- Keep grep patterns simple for better performance.
- Use `origin/<base>...HEAD` (merge-base, three-dot) for committed-scope primary diffs, matching the GitHub PR Files-changed view.
- Use `HEAD` for working-tree primary diffs.
- Use the three-dot merge-base form for the primary committed-scope diff. Avoid the two-dot `origin/<base> HEAD` form as the primary baseline: it includes target-branch commits added after the merge-base and distorts branch delta.
- Do not create review worktrees for the default merge-base baseline. Worktree merge preview is allowed only under `--baseline merge-preview` with a unique `/tmp` path and guaranteed cleanup (`git worktree remove --force` + `git worktree prune`).

## Anti-Patterns to Avoid

- Running diff/stat/log commands before scope is resolved.
- Running committed-scope diff/stat/log commands before PR and build gates are resolved.
- Running working-tree diff/stat commands before git repository and valid `HEAD` checks.
- Treating local `main` as authoritative when `origin/main` has not been fetched.
- Treating `gh pr view --comments` as unresolved review-thread intake.
- Using PR UI diff output as the only committed-scope baseline.
- Using the two-dot `origin/<base> HEAD` form as the primary committed-scope diff (inflates with post-divergence base commits).
