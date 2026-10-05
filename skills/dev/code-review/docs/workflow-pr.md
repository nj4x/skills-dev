# Code Review Workflow: PR Context Steps

Disclosed from [workflow.md](workflow.md). Step numbers match the references in workflow.md and SKILL.md. Read the step the stub in workflow.md points to; read nothing here for `--scope working-tree`.

---

## Step 1.5: PR Context Discovery via GitHub CLI (MANDATORY WHEN `gh` IS AVAILABLE AND `--scope committed`)

> **Scope gate**: If `--scope working-tree`, this step is **skipped entirely**. `PR_INTEGRATION = DISABLED` was already set in Step 1. Proceed to Step 2.

This step is mandatory when `--scope committed` to avoid silent omission of existing PR feedback. If `gh` is available/authenticated, PR context intake MUST be completed before build/diff analysis.

> ⛔ **MANDATORY HARD GATE**: If `gh` is available/authenticated and `--scope committed`, do not continue to Step 2 or any diff/stat/log command until helper-script PR intake is completed or explicitly waived by the user.

> ⛔ **NO SILENT SKIP**: Skipping `gh auth status`, skipping helper-script intake, or failing to record PR state is a workflow violation.

### 1.5.0 Resolution gate (must be satisfied before Step 2)

Before moving to Step 2, record one of these states:
- `PR_INTEGRATION = ENABLED` and `PR_CONTEXT_COLLECTED = YES`
- `PR_INTEGRATION = DISABLED` and `PR_CONTEXT_COLLECTED = NO` with explicit reason

Silent skip is forbidden.

Also record all available PR state fields before Step 2:
- `CURRENT_PR_NUMBER`
- `CURRENT_PR_URL`
- `CURRENT_PR_STATE`
- `PR_UNRESOLVED_THREAD_COUNT`
- `PR_THREAD_TRIAGE_COUNTS`
- `REVIEW_BASE_REF`
- `BASE_REF_SOURCE`

### 1.5.1 Check `gh` availability and auth

```bash
command -v gh >/dev/null && gh auth status
```

- **IF unavailable or unauthenticated**:
  - Set `PR_INTEGRATION = DISABLED`
  - Set `PR_CONTEXT_COLLECTED = NO`
  - Set `PR_INTEGRATION_REASON` with explicit detail (e.g., `gh not installed`, `gh auth failed`)
  - Continue to Step 2.
- **IF available/authenticated**:
  - Set `PR_INTEGRATION = ENABLED`
  - Continue to Step 1.5.2 (mandatory).

### 1.5.2 Discover PR + unresolved threads (mandatory when enabled)

Before running triage, ensure `REVIEW_BASE_REF` is resolved from PR metadata when available. The helper reads `pr.baseRefName` from discover output and falls back to `main`.

Preferred command flow:

```bash
python3 <skill dir>/scripts/code_review_pr_helper.py discover \
  --output /tmp/code-review-pr-discover.json

python3 <skill dir>/scripts/code_review_pr_helper.py triage \
  --discover-json /tmp/code-review-pr-discover.json \
  --output /tmp/code-review-pr-triage.json
```

This helper-script flow is the default and preferred implementation. If `gh` is ready and the helper script exists, using ad-hoc `gh` commands instead of this flow is a workflow violation.

Set (from helper output):
- `CURRENT_PR_NUMBER`, `CURRENT_PR_URL`, `CURRENT_PR_STATE`
- `PR_UNRESOLVED_THREAD_COUNT`
- `PR_THREAD_TRIAGE_COUNTS` (`likely_addressed`, `still_open`, `needs_confirmation`)
- `PR_CONTEXT_COLLECTED = YES`
- `REVIEW_BASE_REF = pr.baseRefName` (fallback `main`)
- `BASE_REF_SOURCE = pr-base` when read from PR metadata, otherwise `fallback-default`

Notes:
- Use `/tmp/...` for intermediate JSON artifacts.
- Keep script path format consistent: `python3 <skill dir>/scripts/...`.
- If PR discovery is ambiguous/missing, re-run with `--pr <number>`.
- If user chooses to continue without PR linkage despite available `gh`, require explicit user waiver and set:
  - `PR_INTEGRATION = DISABLED`
  - `PR_CONTEXT_COLLECTED = NO`
  - `PR_INTEGRATION_REASON = "User waived PR context intake"`

### 1.5.2.1 Helper artifacts + thread coverage gate (mandatory)

Before moving to Step 2, verify ALL of the following are true:
- `/tmp/code-review-pr-discover.json` exists
- `/tmp/code-review-pr-triage.json` exists
- `PR_UNRESOLVED_THREAD_COUNT` was recorded (0 is valid, missing is not)

Recommended verification commands:

```bash
test -f /tmp/code-review-pr-discover.json
test -f /tmp/code-review-pr-triage.json
```

If any item is missing, STOP and either:
- Re-run helper script intake, or
- Record an explicit user waiver and set:
  - `PR_INTEGRATION = DISABLED`
  - `PR_CONTEXT_COLLECTED = NO`
  - `PR_INTEGRATION_REASON = "User waived helper-script PR intake"`

### 1.5.3 Manual fallback (only if helper script unavailable)

If helper script is unavailable, use direct `gh` commands:

```bash
BRANCH=$(git branch --show-current)
gh pr list --head "$BRANCH" --state all --json number,title,url,state,isDraft,reviewDecision
```

Then use GraphQL `reviewThreads` to collect unresolved thread metadata (`path`, `line`/`originalLine`, `isOutdated`, latest comment metadata).

**Never use PR comments as a substitute for review threads.**
- `gh pr view --comments` is NOT a valid replacement for unresolved review threads.
- PR comments are supplemental only and must not be used to satisfy the PR context gate.

### 1.5.3.1 CLI misuse guardrails (mandatory)

The following patterns are forbidden and must not be used:
- `gh pr view <num> --json comments,reviews --comments 10` (invalid flag usage)
- Any `gh` command that mixes `--json` with unsupported flags or pagination flags

Use correct alternatives instead:
- For review threads: GraphQL `reviewThreads` query (helper script preferred)
- For comments (supplemental only): `gh pr view <num> --json comments` (no `--comments` flag)

### 1.5.4 Step gate verification

> ⛔ **HARD STOP**: You MUST print the PR Integration State block below **verbatim in your response text** before proceeding to Step 2. Internal variables are not sufficient — the block must be visible in your output. Do not run any diff, stat, or log commands until this block appears in your response.

Print this block in your response now:

```text
PR Integration State:
  PR_INTEGRATION: [ENABLED|DISABLED]
  PR_CONTEXT_COLLECTED: [YES|NO]
  PR_INTEGRATION_REASON: [detail or N/A]
  CURRENT_PR_NUMBER: [number or N/A]
  CURRENT_PR_URL: [url or N/A]
  CURRENT_PR_STATE: [state or N/A]
  PR_UNRESOLVED_THREAD_COUNT: [count or N/A]
  PR_THREAD_TRIAGE_COUNTS: [X/Y/Z or N/A]
  REVIEW_BASE_REF: [base branch or main]
  BASE_REF_SOURCE: [pr-base or fallback-default]
  HELPER_ARTIFACT_DISCOVER: [/tmp/code-review-pr-discover.json or N/A]
  HELPER_ARTIFACT_TRIAGE: [/tmp/code-review-pr-triage.json or N/A]
```

Only after this block is present in your response text may you proceed to Step 2.

### 1.5.5 Rules for PR-thread handling

- Never auto-resolve threads.
- Never auto-post comments.
- Never auto-approve PR.
- All PR write actions are **explicit-user-consent only**.

### 1.5.6 Supplemental spec from GitHub issues (committed scope only, when `PROJECT_SRS` is EMPTY)

After PR intake completes, if `PROJECT_SRS` is EMPTY, extract any `#\d+` GitHub issue refs from the PR body and run `gh issue view <n>` for each. Store the fetched issue **body text** as `PROJECT_ISSUE_CONTEXT` and pass it to Step 9 as supplemental spec. Do NOT fetch Jira/Linear keys — bare non-`gh`-fetchable identifiers are dropped, not recorded. (Commit-message `[A-Z]+-\d+:` mining stays in Finder A at Step 4.1; do not duplicate it here.)

---

## Step 4.5: Reconcile Existing Unresolved PR Threads (scope = committed and PR integration enabled)

> **Scope gate**: Skip entirely when `--scope working-tree`.
>
> **PREREQUISITE**: `PR_INTEGRATION = ENABLED` (applies regardless of `PR_UNRESOLVED_THREAD_COUNT` value — even 0 requires the dedupe command so new findings are tagged as "Not yet tracked in PR discussion").

For each unresolved thread (if any), compare comment intent against current `origin/$REVIEW_BASE_REF..HEAD` diff and full method/file context.

Classify each thread:
- **Likely addressed**: code changes appear to resolve the concern
- **Still open**: concern remains unresolved
- **Needs human confirmation**: ambiguous or requires business/context decision

Important:
- This classification is advisory only.
- Do not mark threads resolved automatically.
- Include thread URL in report for quick manual follow-up.

Also de-duplicate findings:
- If a newly discovered issue already exists in unresolved PR comments, tag it as **Already tracked in PR thread**.
- Tag truly new issues as **Not yet tracked in PR discussion**.

Recommended helper command:

```bash
python3 <skill dir>/scripts/code_review_pr_helper.py dedupe \
  --discover-json /tmp/code-review-pr-discover.json \
  --findings /tmp/code-review-findings.json \
  --output /tmp/code-review-pr-dedupe.json
```

---

## Step 13.5: Conditional Mandatory PR Write Actions (EXPLICIT CONSENT REQUIRED)

> ⛔ **CONDITIONAL MANDATORY**: This step MUST be executed when `PR_INTEGRATION = ENABLED` and `CURRENT_PR_NUMBER` is resolved. It is only truly optional when `PR_INTEGRATION = DISABLED`.

### 13.5.0 Script-driven flow (recommended)

Draft review comments from findings:

```bash
python3 <skill dir>/scripts/code_review_pr_helper.py draft-comments \
  --input /tmp/code-review-pr-dedupe.json \
  --only-untracked \
  --output /tmp/code-review-pr-draft-comments.json
```

Publish comments (only after explicit user approval):

```bash
python3 <skill dir>/scripts/code_review_pr_helper.py publish-comments \
  --discover-json /tmp/code-review-pr-discover.json \
  --drafts /tmp/code-review-pr-draft-comments.json \
  --confirm I_UNDERSTAND_POST_TO_PR \
  --output /tmp/code-review-pr-publish-result.json
```

Approve PR (only after explicit user approval):

```bash
python3 <skill dir>/scripts/code_review_pr_helper.py approve \
  --discover-json /tmp/code-review-pr-discover.json \
  --message "Reviewed and approved." \
  --confirm I_UNDERSTAND_APPROVE_PR \
  --output /tmp/code-review-pr-approve-result.json
```

Safety requirements remain mandatory:
- Do not execute `publish-comments` without explicit consent.
- Do not execute `approve` without explicit consent.
- Never auto-resolve PR threads.

### 13.5.1 Offer comment publishing for discovered findings

Ask user:
- which findings to publish (`all`, `selected`, `none`)
- whether to publish as inline comments (preferred) or PR-level summary comment

Before posting, present drafted comment text for approval.

Only after explicit approval, post comments using `gh`.

### 13.5.2 Offer PR approval flow

If verdict is approval-eligible:
- Propose approval message
- Ask user: "Do you want me to approve PR #[number] with this message?"
- Only upon explicit consent, run approval command (e.g., `gh pr review --approve`)

If not approval-eligible:
- Offer to draft request-changes message instead

### 13.5.3 Auditability

Record in final response:
- whether comments were posted
- whether approval was submitted
- exact PR URLs for posted artifacts
