# Code Review Workflow

Analyze code changes against project standards, security patterns, requirement documents, API definitions, module architecture, data views, and tests. Committed scope is the default review policy, but ambiguous invocations must confirm scope before review work starts.

## Parameters

The parameter summary (values, defaults, one-line effects for `--effort`, `--scope`, `--baseline`, `--mode`) is authoritative in [skill.md](../skill.md) *Parameters*. The per-value behavior tables below are the detailed spec.

### `--mode` behavior

| Value | Behavior | Terminal action |
|-------|----------|-----------------|
| `review` *(default)* | Read-only. Runs the full review and produces the report. No repo mutation. | Report delivered. |
| `autofix` | Read-only review through the report, then Step 14 phases RTM-1…RTM-5 (forces `--effort high`). Implements Major/Critical fixes, writes regression tests, runs the testing skill's selective suite to green (full-suite fallback on uncovered files), commits behind a BLOCKING gate. | Stops after commit. |
| `review-to-merge` | `autofix` + RTM-6…RTM-7. Adversarial final review, push (BLOCKING), safe merge to main (BLOCKING). | Stops after merge, or after push if merge unsafe, or earlier at any failed gate. |

Three distinct values, **no synonyms**. An unrecognized or near-miss `--mode` value is not guessed — list the three valid values and ask. Record `REVIEW_MODE` and, when `autofix`/`review-to-merge`, set `REVIEW_MODE_AUTONOMOUS = YES`. Mutating modes require committed-scope semantics for the merge step (see Step 14 RTM-1). The full mutating spec — phases, iteration caps, consent gates, and recovery rows — lives in **Step 14**.

### `--effort` behavior

| Value | Analysis mode | When to use |
|-------|--------------|-------------|
| `low` | Single Explore subagent (Step 4.9) applying the Compliance Reference (Steps 5–10) | Quick check, very small diff, explicit legacy mode |
| `medium` | 4 parallel Explore agents (Step 4.1: Correctness/Security, Architecture/Compliance, Quality/Standards, Maintainability Smells) | Faster review where adversarial verification is not required |
| `high` *(default)* | Fan-out (medium) + adversarial verifier per Critical/Major finding (Step 4.2) | Default — maximum confidence, every Critical/Major finding independently verified |

### `--scope` behavior

| Value | Diff command | Gate behavior |
|-------|-------------|---------------|
| `working-tree` | `git diff HEAD` | Steps 1-1.5 (fetch, divergence, PR) skipped; `PR_INTEGRATION = DISABLED` auto-set |
| `committed` *(default)* | `git diff origin/$REVIEW_BASE_REF...HEAD` | All hard gates active: fetch, divergence check, PR context gate, build/OpenAPI gate |

## Scope Resolution

Resolve scope before repo gates, PR gates, build gates, diff retrieval, or review analysis.

- Explicit `--scope committed` or `--scope working-tree` wins. `--scope uncommitted` is an explicit alias for `working-tree` — accept it directly, never treat it as an unrecognized value.
- Requests mentioning `uncommitted`, `working tree`, `working-tree`, `staged`, `unstaged`, `local changes`, `my diff`, or `pending changes` select `working-tree`.
- Requests mentioning `committed`, `branch`, `commits`, `before push`, `ready to push`, `PR`, or `pull request` select `committed`.
- Ambiguous requests, including bare `/code-review`, must ask: `I can review committed changes, which is the default, or your working tree. Which scope should I use?`

Record `REVIEW_SCOPE`, `REVIEW_EFFORT`, and `REVIEW_MODE` at the start of the review. When `REVIEW_MODE` is `autofix` or `review-to-merge`, also set `REVIEW_MODE_AUTONOMOUS = YES`.

---

## Prerequisites

- Git repository
- When `--scope committed`: current branch is not main, review base branch exists for comparison

## Overview

I will review your committed changes following these steps, keeping you updated on progress as I work.

### Non-negotiable execution order

The review must follow this order exactly:

1. Discover requirement documents
2. Verify repository and branch
3. Resolve `REVIEW_BASE_REF`, then `git fetch origin "$REVIEW_BASE_REF"` AND `git fetch origin <current-branch>`
3.5. Check divergence via `git status` — MANDATORY HARD GATE: if diverged, ask user whether to pull; do not self-decide, do not skip the question
4. Resolve PR context gate
5. Resolve build/OpenAPI gate
6. Only then run diff/stat/log commands and begin code-change analysis
7. **(mutating modes only)** Only after the report is delivered and all gates are green may mutation begin — see the RTM/Autofix prerequisite below and Step 14.

If this order is violated, the review is procedurally incomplete.

> ⛔ **RTM/Autofix prerequisite — non-bypassable.** When `REVIEW_MODE_AUTONOMOUS = YES`, the autonomous mutating phases (Step 14, RTM-1…RTM-7) are *post-report extensions*. They MUST NOT begin until ALL of the following existing hard gates are fully resolved exactly as in `review` mode:
> - **Step 1 / 1.5 branch + divergence gate** — repo verified, base ref fetched, divergence resolved by asking the user (no self-deciding), on-main handled.
> - **Step 1.5 PR-context gate** — PR intake completed or explicitly waived; PR Integration State block printed verbatim.
> - **Step 2 build/OpenAPI gate** — build run and `BUILD_STATUS` resolved. The mutating path does **NOT** start if `BUILD_STATUS` is `FAILED` or `WAIVED` (mutation on an unverified/broken baseline is a safety violation), unless the user explicitly re-confirms risk acceptance *for the mutation specifically*.
> - **Step 4.1 / 4.2 review + adversarial verification** — findings produced and verified (effort is forced to `high`); the structured report (Step 13) generated.
>
> A mutating mode never replaces or skips any read-only gate. The "Forbidden before the gates are resolved" block below applies unchanged; mutation only appends execution step 7 above.

### Forbidden before the gates are resolved

Before both Step 1.5 and Step 2 are resolved, do **not** do any of the following:

- run `git --no-pager diff ...`
- run `git diff ...`
- run `git diff --stat ...`
- run `git log origin/$REVIEW_BASE_REF..HEAD`
- inspect changed files for review findings
- use two-dot `origin/<base> HEAD` as the primary committed-scope review diff
- summarize implementation quality based on the code diff

Allowed early repository setup commands include branch checks, base-ref resolution, fetch, divergence check, `gh auth status`, helper-script PR intake, build commands, and artifact verification.

> ⛔ **NO SELF-DECIDING ON DIVERGENCE**: If `git status` shows the local branch has diverged from or is behind its remote tracking branch, the agent MUST NOT decide for the user whether to pull. It MUST ask the user. Rationalizing away this question ("the intention is to review the current state", "I'll proceed with local HEAD") is a workflow violation.

---

## Step 0: Discover Project Requirement Documents

Before starting the review, locate project requirement documents by running `fd` commands in the project root directory. This step produces 5 variables that will be used in later steps.

### 0.1 Run Discovery Commands

Run ALL five commands below. Each command searches for a specific document type:

```bash
# SRS (Software Requirements Specification)
fd -d 5 '(?i)(srs|software-requirement|software_requirement)' --extension md

# API Definition
fd -d 5 '(?i)(api-definition|api_definition|api-spec|api_spec)' --extension md

# Module View / Architecture
fd -d 5 '(?i)(module-view|module_view|architecture)' --extension md

# Use Case Diagrams
fd -d 5 '(?i)(use-case|use_case|usecase)' --extension md

# Data View (DynamoDB / storage schema)
fd -d 5 '(?i)(data-view|data_view|data-model|data_model|schema)' --extension md
```

### 0.2 Process Results for Each Document Type

For EACH of the 5 document types, apply this decision logic:

**IF exactly 1 file was found:**
- Set the variable to that file path. No user interaction needed.
- Example: `PROJECT_SRS = ./requirements/MyProject-SRS-2.0.md`

**IF 0 files were found:**
- Ask the user: "No [document type] document was found in the project. Please provide the path, or type 'skip' to proceed without it."
- IF user provides a path → set the variable to that path.
- IF user says 'skip' → set the variable to EMPTY. Related review steps will be skipped.

**IF 2 or more files were found:**
- Ask the user: "Multiple [document type] documents found: [list all paths]. Which one should I use for the review? (enter number or path)"
- Set the variable to the user's choice.

### 0.3 Variables Produced by This Step

After processing all 5 document types, you will have these variables:

| Variable | Description | Used In |
|----------|-------------|---------|
| `PROJECT_SRS` | Path to SRS document, or EMPTY | Step 9 |
| `PROJECT_API_DEFINITION` | Path to API Definition document, or EMPTY | Step 8 |
| `PROJECT_MODULE_VIEW` | Path to Module View document, or EMPTY | Step 7 |
| `PROJECT_USE_CASES` | Path to Use Case Diagrams document, or EMPTY | Step 9 |
| `PROJECT_DATA_VIEW` | Path to Data View / DynamoDB schema document, or EMPTY | Step 8.5 |

### 0.4 Report Discovery Results

After all 5 variables are set, report to the user:

```
📄 Project Documents Discovered:
  SRS:            [path or "not found — SRS validation will be skipped"]
  API Definition: [path or "not found — API compliance validation will be skipped"]
  Module View:    [path or "not found — module boundary validation will be skipped"]
  Use Cases:      [path or "not found — use case validation will be skipped"]
  Data View:      [path or "not found — data model/access pattern validation will be skipped"]
```

Proceed to Step 1.

---

## Step 1: Verify Repository and Fetch Latest Review Base

> **Scope gate**: If `--scope working-tree`, skip this entire step. Set:
> - `PR_INTEGRATION = DISABLED`
> - `PR_CONTEXT_COLLECTED = NO`
> - `PR_INTEGRATION_REASON = "working-tree scope — uncommitted changes, no PR"`
>
> Proceed directly to Step 2 (Build Gate).

**IF `--scope committed`:**

```bash
git rev-parse --is-inside-work-tree
git branch --show-current
```

Stop if not in git repository or on main branch.

**Resolve the PR base branch before fetching**. Read `pr.baseRefName` from `/tmp/code-review-pr-discover.json` if PR discovery has already run, else probe `gh pr view --json baseRefName -q .baseRefName`, else fall back to `main`:
```bash
REVIEW_BASE_REF=main   # replace with resolved PR base branch; fallback main
BASE_REF_SOURCE=fallback-default
```

**Fetch the comparison base and current feature branch** to ensure the comparison baseline is up to date:
```bash
git fetch origin "$REVIEW_BASE_REF"
CURRENT_BRANCH=$(git branch --show-current)
git fetch origin "$CURRENT_BRANCH"
```

> ⛔ **MANDATORY HARD GATE — Branch Divergence Check**: This gate MUST be resolved before proceeding to Step 1.5. It is not optional, and the outcome cannot be inferred or assumed.

**Check for branch divergence** after fetching both remotes:
```bash
git status
```

Parse the output for divergence indicators (e.g., `"Your branch and 'origin/...' have diverged"`, `"Your branch is behind"`):

- **IF local branch is behind or diverged from its remote tracking branch**:
  - Report to the user: "⚠️ Your local branch has diverged from `origin/<branch>`. The review will be based on your **local** commits. If you have unpulled remote commits, consider running `git pull` first to ensure the review covers the full up-to-date branch."
  - Ask the user: "Would you like to pull the latest remote changes before I start the review? (yes / no, continue with local)"
  - **IF user says yes** → run `git pull` and re-verify status before continuing
  - **IF user says no** → proceed with local HEAD, but note in the report: "⚠️ Review based on local branch state — remote has unpulled commits"
  - **IF the agent does not ask and self-decides** → this is a workflow violation; the review must restart from this gate
- **IF local branch is up to date with remote** → proceed normally

> ⛔ **On divergence, the only valid action is asking the user the pull question above and waiting for the reply.** Any self-rationalization for proceeding without asking — reviewing "current state", defaulting to local HEAD, or treating divergence as merely informational and noting it in the report — is a workflow violation that restarts the review from this gate.

All subsequent committed-scope diff/log commands use `origin/$REVIEW_BASE_REF`, not local `main`. Because `git diff A...B` computes the merge-base of the local refs, the three-dot result is only PR-accurate after this fetch of `origin/$REVIEW_BASE_REF` and the current branch.

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

## Step 2: Build Project

> ⛔ **MANDATORY HARD GATE**: You MUST complete this step (or have the user explicitly waive it) BEFORE proceeding to Step 3. Do NOT run any git diff or change analysis commands until this step is resolved.
>
> ⛔ **NO SILENT SKIP**: If this step is not executed, the report MUST state the explicit user waiver text and reason.
>
> ⛔ **ORDER ENFORCEMENT**: Step 2 does not replace Step 1.5. Both gates must be resolved before diff/stat/log commands are allowed.

Build the project before reviewing to ensure generated API specifications are up to date and to validate compilation and tests.

### 2.1 Detect Build Tool

Detect the project type by checking for well-known build descriptor files in the project root, in priority order:

```bash
for f in build.gradle build.gradle.kts pom.xml pyproject.toml setup.py package.json Cargo.toml go.mod; do
  [ -f "$f" ] && echo "$f"
done
```

Map the first match to a project type and default build command:

| Detected file | Project type | Default build command | OpenAPI gate |
|---|---|---|---|
| `build.gradle` / `build.gradle.kts` | **Gradle (JVM/Kotlin/Java)** | `./gradlew clean build openapi3` | Required |
| `pom.xml` | **Maven (JVM)** | `mvn clean verify` | Required |
| `pyproject.toml` / `setup.py` | **Python** | `python -m pytest` (activate `.venv` first if present) | NOT APPLICABLE |
| `package.json` | **Node.js / TypeScript** | Check lock file: `npm test` (npm) or `yarn test` (yarn) or `pnpm test` (pnpm) | NOT APPLICABLE |
| `Cargo.toml` | **Rust** | `cargo test` | NOT APPLICABLE |
| `go.mod` | **Go** | `go test ./...` | NOT APPLICABLE |
| none | Unknown | Ask user | Ask user |

**Python projects**: Before running pytest, check for a virtual environment:
```bash
[ -d .venv ] && source .venv/bin/activate || [ -d venv ] && source venv/bin/activate || true
```

**Node.js projects**: Check for a `test` script in `package.json` first:
```bash
rg '"test"' package.json && echo "test script found" || echo "no test script"
```
If no test script is defined, ask the user for the validation command.

**Unknown**: Ask user: "No recognized build descriptor found. Please provide the validation command, or explicitly type `skip with risk accepted` to waive this gate."

Set `PROJECT_TYPE` to the detected type (e.g., `Python`, `Gradle`, `Node.js`, `Unknown`).
Set `OPENAPI_APPLICABLE` to `YES` (Gradle/Maven) or `NO` (all others).

### 2.2 Ask User for Confirmation

Ask the user: "Detected **[PROJECT_TYPE]** project. Build/validation command: `[default command]`. Press Enter to use the default, provide a custom command, or explicitly type `skip with risk accepted` to waive this gate."

For non-JVM projects add: "(OpenAPI artifact verification does not apply to this project type.)"

### 2.3 Validate Build Command Compliance (before running)

**Gradle only** — when `PROJECT_TYPE = Gradle`, command validation is mandatory:

- **Required**: command MUST include `openapi3` task
- **Recommended**: `./gradlew clean build openapi3`
- **Explicitly insufficient**: `./gradlew clean build` (missing OpenAPI generation)
- **Explicitly insufficient**: `./gradlew build -x test` (missing OpenAPI generation)

**If user-provided Gradle command does NOT include `openapi3`:**
- Do NOT execute the command
- Respond that it is non-compliant with the review gate
- Ask for a compliant command (or explicit `skip with risk accepted` waiver)

Non-compliant Gradle command execution is forbidden even if suggested earlier in the conversation.

**All other project types** — no compliance constraint on command format. Set `BUILD_COMMAND_COMPLIANCE = PASS` automatically.

Set `BUILD_COMMAND_COMPLIANCE = PASS/FAIL`.

### 2.4 Run Build

**IF user provides a command or accepts the default** → Run it.

- **IF build succeeds** → Set `BUILD_STATUS = SUCCESS`.
  - If `OPENAPI_APPLICABLE = YES` → Continue to Step 2.5 (OpenAPI artifact verification).
  - If `OPENAPI_APPLICABLE = NO` → Set `OPENAPI_STATUS = NOT_APPLICABLE`. Proceed to Step 3.
- **IF build fails** → Set `BUILD_STATUS = FAILED` and `OPENAPI_STATUS = UNKNOWN`. Report build failure as a **🔴 CRITICAL finding** in the final report. Ask user: "Build/tests failed. Would you like to continue the code review anyway in partial mode?" If yes, proceed to Step 3 with `REVIEW_MODE = PARTIAL`. If no, stop the review.
- **IF build times out and `OPENAPI_APPLICABLE = YES`** → Do NOT assume success or failure. Immediately run:
  ```bash
  fd -p 'openapi3.yaml' build
  ```
  - **IF artifact found** → Set `BUILD_STATUS = SUCCESS` and continue to Step 2.5.
  - **IF artifact NOT found** → Set `BUILD_STATUS = TIMED_OUT` and `OPENAPI_STATUS = UNKNOWN`. Ask user: "The build timed out and the OpenAPI artifact was not found. Would you like to re-run the build, continue in partial mode, or stop the review?" Do not proceed to diff analysis until the user responds.
- **IF build times out and `OPENAPI_APPLICABLE = NO`** → Set `BUILD_STATUS = TIMED_OUT`, `OPENAPI_STATUS = NOT_APPLICABLE`. Ask user: "The build/test run timed out. Would you like to re-run, continue in partial mode, or stop the review?"

**IF user explicitly says `skip with risk accepted`** → Set `BUILD_STATUS = WAIVED`, `OPENAPI_STATUS = WAIVED`, and `REVIEW_MODE = PARTIAL`. Proceed to Step 3. Note in the report: "⚠️ Build gate waived by user with risk accepted — tests may be failing or specs may be stale."

### 2.5 Verify OpenAPI Artifacts (Gradle/Maven only — skip for other project types)

> **Scope gate**: Skip this step entirely when `OPENAPI_APPLICABLE = NO`. Set `OPENAPI_STATUS = NOT_APPLICABLE` and proceed to Step 3.

When `BUILD_STATUS = SUCCESS` and `OPENAPI_APPLICABLE = YES`, verify generated OpenAPI files exist:

```bash
test -f build/api-spec/openapi3.yaml && ls build/api-spec/*.yaml 2>/dev/null
```

- **IF artifacts found** → Set `OPENAPI_STATUS = VERIFIED`. Proceed to Step 3.
- **IF artifacts missing** → Set `OPENAPI_STATUS = MISSING`. Report as **🔴 CRITICAL**: "Build succeeded but OpenAPI artifacts were not generated/found." Ask user if review should continue in `REVIEW_MODE = PARTIAL`.

Important:
- `build/generated-snippets/**` is NOT a substitute for OpenAPI artifact verification.
- Canonical verification target is `build/api-spec/openapi3.yaml` (or explicit repo-specific canonical path).

### 2.6 Verify New Endpoint Coverage in Generated Spec (Gradle/Maven only — skip for other project types)

> **Scope gate**: Skip this step entirely when `OPENAPI_APPLICABLE = NO`. Set `OPENAPI_ENDPOINT_COVERAGE = NOT_APPLICABLE` and proceed to Step 3.

If `OPENAPI_APPLICABLE = YES` and changed files include controllers, path constants, request/response API models, or OpenAPI config files:

1. Identify expected new/changed endpoint paths from diff
2. Verify those paths are present in generated OpenAPI spec files (for example):

```bash
rg '^\s*(/internal/groups/teacher:|/v2/)' build/api-spec/openapi3.yaml
```

- **IF expected endpoints are present** → Set `OPENAPI_ENDPOINT_COVERAGE = VERIFIED`
- **IF missing** → Set `OPENAPI_ENDPOINT_COVERAGE = MISSING` and report as **🔴 CRITICAL**

---

## Step 3: Get Change Statistics

> **PREREQUISITE GATE**: Step 2 must be resolved with one of:
> - (`BUILD_STATUS = SUCCESS` and `OPENAPI_STATUS = VERIFIED` and `OPENAPI_ENDPOINT_COVERAGE != MISSING`), or
> - explicit user waiver (`BUILD_STATUS = WAIVED`), or
> - explicit user approval to continue in partial mode after failure/missing artifacts.
>
> **PR CONTEXT GATE**: Step 1.5 must also be resolved with one of:
> - (`PR_INTEGRATION = ENABLED` and `PR_CONTEXT_COLLECTED = YES`), or
> - (`PR_INTEGRATION = DISABLED` and `PR_CONTEXT_COLLECTED = NO` with explicit `PR_INTEGRATION_REASON`)
>
> Do NOT run diff commands until both gates are satisfied.

If a prior attempt already ran diff/stat/log commands before both gates were satisfied, restart the review sequence from the first unresolved gate and do not rely on the premature analysis.

**IF `--scope working-tree`**:
```bash
git --no-pager diff --stat HEAD
git --no-pager diff --shortstat HEAD
```
(No `git log` command — changes are uncommitted.)

**IF `--scope committed`** (default):
```bash
git --no-pager diff --stat "origin/$REVIEW_BASE_REF...HEAD"
git --no-pager diff --shortstat "origin/$REVIEW_BASE_REF...HEAD"
git merge-base "origin/$REVIEW_BASE_REF" HEAD   # record the merge-base SHA for the report
git log "origin/$REVIEW_BASE_REF..HEAD" --pretty=format:"%h - %s"   # two-dot range: commits unique to HEAD (do NOT change to three-dot)
```

The committed-scope `diff` uses the three-dot `origin/$REVIEW_BASE_REF...HEAD` form so the counts match the GitHub PR Files-changed view. `git diff A...B` computes the merge-base of local refs, so this is only PR-accurate after the Step 1 fetch of `origin/$REVIEW_BASE_REF` and the current branch. The `git log` range stays two-dot (`..`) on purpose.

Parse output for:
- File count
- Total line changes
- Commit messages

**Size classification:**
- **SMALL**: ≤10 files + ≤500 lines
- **MEDIUM**: 11-30 files OR 501-2000 lines
- **LARGE**: 30+ files OR 2000+ lines

Stop if no changes found.

---

## Step 4: Get Diff (Size-Based)

**SMALL and MEDIUM changesets:**

*If `--scope working-tree`:*
```bash
git --no-pager diff HEAD
```

*If `--scope committed`:*
```bash
git --no-pager diff "origin/$REVIEW_BASE_REF...HEAD"
```

**LARGE changesets:**
Ask user preference:
1. Priority review (security + architecture patterns only)
2. Targeted review (user picks specific files/packages)
3. Multi-pass review (critical → major → minor)

### 4.0.1 Optional merge-preview baseline (`--baseline merge-preview` only)

Do not run this block for the default `--baseline merge-base`.

1. Create a disposable worktree with a unique `/tmp` path:
   ```bash
   git worktree add /tmp/cr-merge-preview-$$ -b cr-merge-preview-$$
   ```
2. Inside the worktree, attempt the base merge without committing:
   ```bash
   git merge origin/$REVIEW_BASE_REF --no-commit --no-ff
   ```
3. Treat merge conflicts as findings (Major severity, Architecture/Merge-Safety category).
4. Guaranteed cleanup on both success and failure paths:
   ```bash
   git worktree remove --force /tmp/cr-merge-preview-$$
   git worktree prune
   ```
5. Do not leave worktrees behind; do not use this block for `--baseline merge-base`.

---

## Step 4.1: Multi-Angle Fan-Out Review (effort ≥ medium)

> **Effort gate**: Skip this step when `--effort low`. For `--effort low`, see Step 4.9 (single subagent path).
>
> When `--effort medium` or `--effort high`: Steps 5–10 are **replaced** by this step. Spawn the 4 agents below concurrently, then synthesize into a unified finding list and proceed to Step 4.2 (if high) or Step 11 (if medium).

Spawn 4 Explore agents **in parallel**. Pass each agent:
- The full diff text from Step 4
- All discovered document paths: `PROJECT_SRS`, `PROJECT_API_DEFINITION`, `PROJECT_MODULE_VIEW`, `PROJECT_DATA_VIEW`
- The `--scope` value (so agents know whether Jira commit-message validation applies)

### Finder A — Correctness & Security

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angles are **Correctness** and **Security**:
> - Correctness: logic bugs, off-by-one errors, incorrect error handling, removed behavior that callers rely on, stale-data risks, race conditions, data mutation from ambiguous input
> - Security: hardcoded credentials/secrets/tokens, PII in logs, SQL/command injection, weak auth, insecure CORS, exposed internals
> - When `--scope committed`: also check commit messages for Jira ticket reference pattern `[A-Z]+-\d+:` at start (MAJOR if missing)
> - When PROJECT_SRS is available: check business rule enforcement in use-case logic against the SRS
>
> For each finding, return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix`.
> Return findings as a structured list. Do NOT include findings you are not confident about — prefer omission over false positives.

### Finder B — Architecture & Compliance

Pre-read (before reviewing the diff):
1. Read `~/.claude/skills/improve-codebase-architecture/SKILL.md` — for the deep-module detection lens and deletion test.
2. Read `~/.claude/skills/codebase-design/SKILL.md` — for the canonical vocabulary: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**. Use these terms exactly in all findings — not "component," "service," "API," or "boundary."
3. Read `~/.claude/skills/codebase-design/DEEPENING.md` — for dependency classification and seam discipline.

Bounded context (before applying the deep-module lens):
- If PROJECT_MODULE_VIEW is set: for each changed file, identify its module boundary per the MODULE_VIEW document and read all source files in that module.
- Otherwise: for each changed file, read all source files in its parent directory (package-prefix fallback).
- READ-ONLY — do not walk the full codebase.

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angles are **Architecture**, **Compliance**, and **Deep-Module Detection**:
>
> **Architecture & Compliance (unchanged):**
> - Architecture: module boundary violations, circular dependencies, wrong-layer access (entity leaking beyond repository), field injection anti-patterns, N+1 queries, missing pagination, DynamoDB Limit+FilterExpression misuse
> - API compliance: HTTP method/path/error-code alignment with PROJECT_API_DEFINITION, OpenAPI annotation completeness, API documentation parity (consistent-or-better vs API Definition text). Apply the framework-validation `BAD_REQUEST` allowance and the API-doc severity policy from workflow.md Steps 8.x.1 and 8.y — read them before grading any error-code or documentation mismatch.
> - Data View compliance: PK/SK prefixes, GSI count/names/projections, attribute naming, access-pattern mapping — validate against PROJECT_DATA_VIEW when DDB entities/repos/configs are changed. Grade per the Data View severity policy and pre-existing-vs-in-scope rule in workflow.md Steps 8.5.1 and 8.5.2.
> - Cross-file duplication: identify near-identical logic that can be extracted
>
> **Deep-Module Detection (use vocabulary from pre-read skill docs — apply to the diff only, never flag pre-existing debt the diff leaves untouched):**
>
> *Scenario 1 — Diff creates a new shallow module:*
> Apply the deletion test to every new module introduced by the diff: would deleting it concentrate complexity back into callers (deep) or just move it (shallow)? If shallow → MAJOR.
> Description format: `Module '<name>' is shallow (interface ≈ implementation complexity; deletion test: deleting it moves complexity rather than concentrating it). Deepening sketch: <one-line suggestion using codebase-design vocabulary>.`
>
> *Scenario 2 — Diff deepens an existing module:*
> If the diff reduces interface surface, introduces a seam, or pulls logic behind an interface:
> - Deepening complete (interface genuinely simpler, implementation absorbs complexity) → POSITIVE.
>   Description: `Module '<name>' deepened: interface surface reduced — good locality gain. (<vocabulary term> applied correctly.)`
> - Deepening incomplete (seam still leaky, interface still cluttered) → MAJOR.
>   Description: `Module '<name>' partially deepened but seam is still leaky: <what remains exposed>. To complete: <one-line sketch>.`
>
> For each finding, return: `severity` (CRITICAL/MAJOR/MINOR/POSITIVE), `file:line`, `description`, `recommended fix` (or `what's good` for POSITIVE).
> Do NOT include findings you are not confident about.

### Finder C — Quality & Standards

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angles are **Quality** and **Standards**:
> - Kotlin idioms: `data class` with `val`, extension functions, sealed interfaces, `checkNotNull {}`, named constants
> - Simplification: dead code, over-engineering, redundant abstractions, unused variables
> - Efficiency: unnecessary allocations, repeated computations, missing batching
> - Testing standards: correct framework (Kotlin Test over JUnit), MockK type-erasure pitfall (`match {}` vs `any<T>()`), test naming conventions, test independence, event exhaustiveness checks
> - Altitude cleanup: magic strings, TODO comments without tracking, stale/misleading comments
>
> For each finding, return: `severity` (CRITICAL/MAJOR/MINOR/NOTE/POSITIVE), `file:line`, `description`, `recommended fix` (or `what's good` for POSITIVE).
> Do NOT include findings you are not confident about.

### Finder D — Maintainability Smells

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Maintainability Smells** from Fowler's _Refactoring_, chapter 3.
> First read `~/.claude/skills/code-review/docs/smell-baseline.md` — the canonical 12-smell catalogue and its binding rules (repo overrides baseline, skip tooling-enforced smells, Notes-only, judgement-call standard). Apply them exactly.
> **De-dup precedence for this roster:** if Finder A, B, or C already reported the same `file:line` at a higher severity, skip the smell — do not double-report.
> For each finding, return: `severity = NOTE`, `file:line`, `smell name`, `description`, `suggested fix`.
> Do NOT include findings you are not confident about.

### Synthesis

After all 4 finders complete:
1. Merge all findings into a single list.
2. Deduplicate: if two agents reported the same issue at the same file:line, keep the higher-severity entry. Finder D (Smell) Notes always lose to any Finder A/B/C finding at the same file:line — drop the Note.
3. Sort: CRITICAL → MAJOR → MINOR → NOTE → POSITIVE.
4. If `--effort medium`: proceed to Step 10.5 (Lineage Enforcement), then Step 11 (Categorize Findings) with this list.
5. If `--effort high`: proceed to Step 4.2 (Adversarial Verification). Finder D Notes are never sent to verifiers.

### Mandatory Pre-Report Verification Protocol

Every Minor/Major/Critical finding must include evidence. Before reporting a finding, verify the actual code path or contract:

1. For missing validation, logic, or checks, trace the dependency chain. Open readers, validators, utilities, and injected services before claiming the logic is absent.
2. For unused imports, dead code, variables, or constants, open the exact file and grep for the symbol in that file.
3. For idiom/style suggestions, open the cited standard and read the full rule including exceptions or `When NOT to apply` clauses.
4. For API, SRS, or Data View contract claims, quote the exact spec line that the code contradicts.
5. Distinguish defects from preferences. If the code works and breaks no rule, report it as Note or drop it.

If evidence cannot be produced, drop the finding or downgrade it to Note.

---

## Step 4.1-RTM: Four-Agent Review Profile (mutating modes only)

> **Mode gate**: Runs only when `REVIEW_MODE_AUTONOMOUS = YES` (`--mode autofix` or `review-to-merge`). In that case this profile **replaces** the 4 A/B/C/D finders of Step 4.1 — do not run both rosters. Effort is forced to `high`, so Step 4.2 adversarial verification always follows.

Spawn 5 Explore agents **in parallel** (READ-ONLY for this discovery phase). Pass each agent the same inputs as Step 4.1 (full diff, `PROJECT_SRS`, `PROJECT_API_DEFINITION`, `PROJECT_MODULE_VIEW`, `PROJECT_DATA_VIEW`, the `--scope` value). The five angles isolate **Tests/Regressions** and **Operational risk** as first-class lanes because the mutating path will *write* regression tests and *merge*. Smells run in their own dedicated agent so they never inflate the per-agent context of the functional review lanes.

### Agent 1 — Correctness & Edge Cases

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Correctness & Edge Cases**: logic bugs, off-by-one and boundary conditions, null/empty/overflow handling, incorrect error handling, removed behavior callers rely on, stale-data risks, race conditions, data mutation from ambiguous input.
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix`. Omit findings you are not confident about.

### Agent 2 — Tests & Regressions

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Tests & Regressions**: missing coverage for changed paths, regressions introduced by the diff, brittle/flaky tests, test gaps per changed function, framework/standards adherence (Kotlin Test over JUnit, MockK `match {}` vs `any<T>()`; pytest patterns for Python), test independence, event-exhaustiveness checks. For each changed function lacking a regression test, name the test that should exist.
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix` (or the missing test to add). Omit findings you are not confident about.

### Agent 3 — Architecture & Maintainability

Pre-read (before reviewing the diff):
1. Read `~/.claude/skills/improve-codebase-architecture/SKILL.md` — for the deep-module detection lens and deletion test.
2. Read `~/.claude/skills/codebase-design/SKILL.md` — for the canonical vocabulary: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**. Use these terms exactly in all findings — not "component," "service," "API," or "boundary."
3. Read `~/.claude/skills/codebase-design/DEEPENING.md` — for dependency classification and seam discipline.

Bounded context (before applying the deep-module lens):
- If PROJECT_MODULE_VIEW is set: for each changed file, identify its module boundary per the MODULE_VIEW document and read all source files in that module.
- Otherwise: for each changed file, read all source files in its parent directory (package-prefix fallback).
- READ-ONLY — do not walk the full codebase.

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angles are **Architecture & Maintainability** and **Deep-Module Detection**:
>
> **Architecture & Maintainability (baseline):**
> - Module boundary violations, circular dependencies, wrong-layer access, field-injection anti-patterns, duplication that should be extracted
> - Naming, complexity, dependency direction, dead code, over-engineering
> - N+1 queries, missing pagination, DynamoDB Limit+FilterExpression misuse
> - API + Data View compliance when PROJECT_API_DEFINITION / PROJECT_DATA_VIEW is provided and the diff touches controllers/API models or DDB entities/repos/configs: grade per the severity policies and allowances in workflow.md Steps 8.x.1, 8.y, 8.5.1, and 8.5.2 — read them before grading any API-doc or Data View mismatch.
>
> **Deep-Module Detection (use vocabulary from pre-read skill docs — apply to the diff only, never flag pre-existing debt the diff leaves untouched):**
>
> *Scenario 1 — Diff creates a new shallow module:*
> Apply the deletion test to every new module introduced by the diff: would deleting it concentrate complexity back into callers (deep) or just move it (shallow)? If shallow → MAJOR.
> Description format: `Module '<name>' is shallow (interface ≈ implementation complexity; deletion test: deleting it moves complexity rather than concentrating it). Deepening sketch: <one-line suggestion using codebase-design vocabulary>.`
>
> *Scenario 2 — Diff deepens an existing module:*
> If the diff reduces interface surface, introduces a seam, or pulls logic behind an interface:
> - Deepening complete (interface genuinely simpler, implementation absorbs complexity) → POSITIVE.
>   Description: `Module '<name>' deepened: interface surface reduced — good locality gain. (<vocabulary term> applied correctly.)`
> - Deepening incomplete (seam still leaky, interface still cluttered) → MAJOR.
>   Description: `Module '<name>' partially deepened but seam is still leaky: <what remains exposed>. To complete: <one-line sketch>.`
>
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR/POSITIVE), `file:line`, `description`, `recommended fix` (or `what's good` for POSITIVE). Omit findings you are not confident about.

### Agent 4 — Security & Operational Risk

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Security & Operational Risk**: hardcoded secrets/tokens, PII in logs, SQL/command injection, weak auth, insecure CORS, exposed internals — PLUS operational concerns relevant to autonomously merging this change: migration/rollback safety, config and feature-flag risk, idempotency, observability/logging gaps, and merge-safety (anything that would be unsafe to land on main).
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR), `file:line`, `description`, `recommended fix`. Omit findings you are not confident about.

### Agent 5 — Maintainability Smells

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angle is **Maintainability Smells** from Fowler's _Refactoring_, chapter 3.
> First read `~/.claude/skills/code-review/docs/smell-baseline.md` — the canonical 12-smell catalogue and its binding rules (repo overrides baseline, skip tooling-enforced smells, Notes-only, judgement-call standard). Apply them exactly.
> **De-dup precedence for this roster:** skip a `file:line` if Agents 1, 2, 3, or 4 already reported it at any severity.
> For each finding return: `severity = NOTE`, `file:line`, `smell name`, `description`, `suggested fix`. Omit findings you are not confident about.

### Synthesis (shared)

Reuse the Step 4.1 **Synthesis** and **Mandatory Pre-Report Verification Protocol** blocks verbatim (merge, dedupe by `file:line` keeping higher severity with Agent 5 Notes always losing to any Agent 1–4 finding at the same file:line; sort CRITICAL → MAJOR → MINOR → NOTE → POSITIVE; Agent 5 Notes are never sent to the adversarial verifier). Then proceed to Step 4.2 (adversarial verification — always runs, effort is `high`).

---

## Step 4.2: Adversarial Verification (effort = high only)

> **Effort gate**: Only runs when `--effort high`. Skip when `--effort low` or `--effort medium`.

For each **CRITICAL or MAJOR** finding from Step 4.1, spawn a targeted Explore agent (up to 4 concurrently; batch remaining findings if more than 4):

Prompt template:
> You are an adversarial code reviewer. Your job is to **refute** the finding below if possible.
> Read the relevant file(s) at the exact line(s) cited. Read enough surrounding context (the full method and any callsites if needed) to make a definitive judgment.
> **Default to REFUTED if uncertain** — the burden of proof is on confirmation.
>
> Finding:
> - File: `[file:line]`
> - Severity: `[CRITICAL|MAJOR]`
> - Description: `[description]`
> - Recommended fix: `[fix]`
>
> Return one of:
> - `CONFIRMED` — the finding is definitely real; the code has this problem
> - `PLAUSIBLE` — the finding is likely real but requires runtime or context not visible in static analysis
> - `REFUTED` — the finding is wrong, already handled, or inapplicable

**Outcome mapping:**
- `CONFIRMED` or `PLAUSIBLE` → include in main report at stated severity
- `REFUTED` → move to `### 🔍 Candidate Issues (Not Confirmed)` section in the report; exclude from grade calculation

> MINOR findings are **not** sent to verifiers (cost vs benefit). They proceed directly to Step 11.

After all verifier agents complete, proceed to Step 10.5 (Lineage Enforcement), then Step 11 (Categorize Findings) with the verified finding list.

---

## Step 4.9: Data Collection Complete — Spawn Review Subagent(s)

> ⛔ **MANDATORY TRANSITION**: All prerequisite data (diff, file contents, commit log) is now collected. For ALL effort levels, code analysis runs in subagents — never inline in the orchestrator.

**IF `--effort low`**: Spawn a single general-purpose Explore subagent. Pass it:
- The complete diff text from Step 4
- All discovered document paths: `PROJECT_SRS`, `PROJECT_API_DEFINITION`, `PROJECT_MODULE_VIEW`, `PROJECT_DATA_VIEW`
- The `--scope` value (so it knows whether Jira commit-message validation applies)
- Pre-read instructions:
  1. Read `~/.claude/skills/improve-codebase-architecture/SKILL.md` — for the deep-module detection lens and deletion test.
  2. Read `~/.claude/skills/codebase-design/SKILL.md` — for the canonical vocabulary: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**. Use these terms exactly in findings.
  3. Read `~/.claude/skills/codebase-design/DEEPENING.md` — for dependency classification and seam discipline.
  4. Read `~/.claude/skills/code-review/docs/smell-baseline.md` — the canonical 12-smell catalogue and binding rules for the maintainability-smells dimension.
- This analysis brief:

> You are a high-recall code reviewer (READ-ONLY). Analyze the diff against all dimensions below and return a unified finding list.
>
> **Commit messages** (committed scope only): check each commit message for Jira ticket reference `[A-Z]+-\d+:` at start — MAJOR if missing.
>
> **Kotlin/language standards**: vertical-slice pattern (UseCase `@Service` with `operator fun invoke()`, thin controllers, constructor injection only); three-tier model (API models → Resources → Entities, no entity leaking beyond repository); `@JsonIgnoreProperties(ignoreUnknown = true)` on request models but NOT response models; Kotlin idioms (`data class` with `val`, extension functions, sealed interfaces, `checkNotNull {}`); custom validators in `validator/` sub-package; centralized `@RestControllerAdvice`.
>
> **Module architecture** (when MODULE_VIEW provided): zero circular dependencies; module boundaries respected per Module View; shared modules have no dependencies on feature modules; cross-module reads go through interfaces.
>
> **Deep-Module Detection (apply to the diff only, never flag pre-existing debt):**
> - *New shallow modules*: Apply the deletion test — would deleting it concentrate complexity back into callers (deep) or just move it (shallow)? If shallow → MAJOR.
> - *Deepening existing modules*: If diff reduces interface surface, introduces a seam, or pulls logic behind an interface: Deepening complete (interface simpler, implementation absorbs complexity) → POSITIVE. Deepening incomplete (seam still leaky, interface still cluttered) → MAJOR.
> Use codebase-design vocabulary (module, interface, depth, seam, adapter, leverage, locality) in all deep-module findings.
>
> **API compliance** (when API_DEFINITION provided): HTTP method + path matches spec; request/response fields correct; error codes correct; pagination follows project pattern; OpenAPI annotations present; API documentation semantically consistent-or-better vs API Definition. Apply the framework-validation `BAD_REQUEST` allowance and API-doc severity policy from workflow.md Steps 8.x.1 and 8.y before grading any error-code or documentation mismatch.
>
> **Data View compliance** (when DATA_VIEW provided, if DDB entities/repos/constants changed): PK/SK prefixes match; GSI count/names/projections match; attribute naming correct; access-pattern mapping to Data View; transactional semantics correct. Grade per the Data View severity policy and pre-existing-vs-in-scope rule in workflow.md Steps 8.5.1 and 8.5.2.
>
> **Business logic** (when SRS provided, for UseCase/validator/event-handler changes): business rules enforced; authorization correct; state transitions respected; events published correctly. Apply 2x severity multiplier for UseCase findings.
>
> **Testing standards**: Kotlin Test over JUnit; MockK `match {}` vs `any<T>()` pitfall; backtick descriptive names; correct test types per class; event exhaustiveness checks; test independence.
>
> **Maintainability smells** (Fowler ch.3 — always Notes, never grade-affecting): apply the canonical 12-smell catalogue and binding rules from the pre-read `~/.claude/skills/code-review/docs/smell-baseline.md`. Only raise a smell you can name concretely with a specific code location.
>
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR/NOTE/POSITIVE), `file:line`, `description`, `recommended fix` (or `what's good` for POSITIVE). Prefer omission over false positives.

Wait for the agent to return findings, then proceed to Step 10.5 (Lineage Enforcement), then Step 11 with the unified finding list.

**IF `--effort medium` or `--effort high`**: Steps 5–10 are replaced by Step 4.1 (fan-out agents). You MUST have already completed Step 4.1 (and Step 4.2 for high, which also routes to Step 10.5) before reaching this point. Proceed directly to Step 11 with the synthesized/verified finding list.

> The following are forbidden at this point regardless of effort level:
> - Doing inline analysis in the orchestrator instead of delegating to a subagent
> - Stopping to ask the user for permission to continue
> - Re-verifying artifacts already confirmed in Steps 1–2
> - Collecting additional files or commands not required by the current analysis path
> - Pausing between steps to report intermediate progress
>
> After subagent(s) return, proceed to Step 10.5 (Lineage Enforcement), then Step 12 (grade) and Step 13 (report). The report is the deliverable — produce it without waiting for user prompts.

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

# Compliance Reference (Steps 5–10)

> ⛔ **These are NOT orchestrator steps.** All effort levels analyze via subagents (Step 4.1 finders, or the Step 4.9 single subagent), never inline. This section is the **detailed compliance reference** those subagents consult. The Finder prompts point here for the parts they cannot carry inline — the framework-validation `BAD_REQUEST` allowance (Step 8.x.1), the Data View severity policy (Step 8.5.1), and the API documentation severity policy (Step 8.y). Step 10.5 (Lineage) below is the one exception: it is a real orchestrator step, run per Step 4.1/4.2/4.9 routing.

## Step 5: Validate Commit Messages

> **Scope gate**: Only applies when `--scope committed`. Skip when `--scope working-tree` (changes are uncommitted, no commit messages to validate).

Check each commit in `origin/$REVIEW_BASE_REF..HEAD` (two-dot range: commits unique to this branch) for Jira ticket reference:
- Pattern: `[A-Z]+-\d+:` at start
- **🟠 MAJOR issue** if missing

---

## Step 6: Kotlin Coding Standards

Validate code against the project's established Kotlin conventions.

**Key areas to check:**
- [ ] **Vertical Slice**: UseCases are `@Service` with `operator fun invoke()`. Controllers are thin (no business logic). Constructor injection only — no `@Autowired` on fields.
- [ ] **Three-Tier Model**: API models → Resources → Entities. Entities must NOT leak beyond `RepositoryImpl`. Repositories accept/return Resources only. Tier conversions via extension functions.
- [ ] **Request/Response models**: Request models use `@JsonIgnoreProperties(ignoreUnknown = true)`. Response models do NOT (they are serialized, not deserialized).
- [ ] **Kotlin idioms**: `data class` with `val`, extension functions for conversions, sealed interfaces for events, `checkNotNull {}` for preconditions, named constants (not magic strings).
- [ ] **Validation**: Custom validators in `validator/` sub-package, validation at API layer via `@Valid @RequestBody`. `isValid(null) = false` is **correct** for required fields — do NOT flag as dead code.
- [ ] **Error handling**: Extend base exception class, use `ErrorCode` enum, centralized `@RestControllerAdvice`. Never expose stack traces.
- [ ] **Events**: Sealed `Event` hierarchy, critical vs non-critical distinction, Kafka headers, exhaustiveness enforced in tests.
- [ ] **DynamoDB**: AWS SDK v2 Enhanced Client, no `AttributeValue` leaking outside repository, `@DynamoDbVersionAttribute` for optimistic locking.

→ See [kotlin-standards.md](kotlin-standards.md) for full standards, examples, and anti-patterns.

#### Python Projects (`PROJECT_TYPE = Python`)

> This is a per-language addendum to the inline (effort=low) review path. It does **not** replace the Kotlin/JVM guidance above — apply it only when `PROJECT_TYPE = Python`.

When reviewing Python code, apply standards from [python-standards.md](python-standards.md):

**Pydantic & Type Annotations**
- All validators use `@field_validator`/`@model_validator` (pydantic v2) — flag any legacy `@validator`/`@root_validator`
- `from typing import List/Dict/Optional/Iterator` → flag as deprecated; require `collections.abc` / built-ins
- Missing `__all__` on public `__init__.py` modules → flag as MINOR
- `TYPE_CHECKING` import pattern for type-only cross-module refs — verify it is used where needed

**DRY & Code Quality**
- Three or more near-identical code blocks → flag as MINOR with suggested abstraction
- Repeated audit-detail dicts with same base keys → flag, suggest `_build_audit` helper
- Inline `str.partition(":")` typed-id parsing → flag if `parse_typed_id` helper exists in `schemas/`
- `str(exc)` / raw exception text in audit records or user-visible output → flag as MINOR (m-2 pattern)

**SQL / DB**
- f-string or `%`-format SQL with variable identifiers → flag as MAJOR (psycopg2.sql.Identifier required)
- All values must be parameterized (`%s`) → any string-interpolated value is CRITICAL

**Testing**
- `except Exception: pass` or `except Exception as e: pass` (unused binding) in conftest teardown → flag as MINOR
- Non-parametrized near-duplicate test bodies → flag as MINOR
- `from typing import Iterator` in test fixtures → flag as MINOR

---

## Step 7: Module Architecture & Boundaries

> **PREREQUISITE**: This step requires `PROJECT_MODULE_VIEW`.
> **IF `PROJECT_MODULE_VIEW` is EMPTY**: Skip this entire step. Add to the report: "⚠️ Module View document not found — module boundary validation was skipped."

**IF `PROJECT_MODULE_VIEW` is set**: Read the file at `PROJECT_MODULE_VIEW` and validate changes against the module architecture defined in it.

**Essential rules to check (adapt based on what the Module View document defines):**
- **Zero circular dependencies** — modules depend downward only
- **Module boundaries** are respected as defined in the Module View
- **Shared modules** (e.g., `common/`) have no dependencies on feature modules
- **Dependency modules** (e.g., `dependencies/`) contain external API clients only
- **Cross-module reads** go through interfaces, not direct module access
- **Event consumers** use dependency inversion — handlers depend on interfaces, not on feature modules
- **One-way dependencies only** as specified in the Module View dependency matrix

---

## Step 8: API Definition Compliance

> **PREREQUISITE**: This step requires `PROJECT_API_DEFINITION`.
> **IF `PROJECT_API_DEFINITION` is EMPTY**: Skip the specification validation parts of this step. Add to the report: "⚠️ API Definition document not found — API specification validation was skipped."

**IF `PROJECT_API_DEFINITION` is set**: When changes touch Controllers, API models (request/response DTOs), path constants, or error codes — read the file at `PROJECT_API_DEFINITION` and validate against it.

**What to check:**
- HTTP method + path matches the specification
- Request/response field names, types, optionality, and constraints match
- Error codes and HTTP status codes are correct (with framework-validation allowance below)
- Pagination follows the project's established pattern
- Path parameter semantics are correct
- Gateway-injected headers are used correctly
- API category paths are respected (e.g., `/internal/` for service-to-service, `/v2/` for admin, `/v2/me/` for self-service)
- OpenAPI documentation annotations are present and accurate
- **Generated API specifications are present and include new endpoints**
  - Look for generated spec files (e.g., `build/api-spec/openapi3.yaml` or similar)
  - **CRITICAL**: API specifications MUST be present and MUST contain all APIs under development
  - **IF `BUILD_STATUS = SUCCESS`** and spec files are still missing or incomplete → this is a **🔴 CRITICAL** violation (the build ran but specs were not generated properly)
  - **IF `BUILD_STATUS = WAIVED`** and spec files are missing → note in the report: "⚠️ API specs not found and build/OpenAPI gate was waived in Step 2 — re-run the review with a build to validate API specifications"
  - **CRITICAL**: If new endpoints are missing from specifications, this is a critical violation
- **API documentation quality parity (consistent or better) vs API Definition**
  - Method documentation (summary/description/comments) must be semantically consistent with API Definition documentation
  - Payload documentation for request/response fields must preserve API Definition meaning (intent, constraints, required/optional semantics)
  - More detailed documentation is allowed and encouraged, as long as it does not contradict the API Definition
  - Missing key meaning/constraint from API Definition in implementation docs is considered a quality defect

### 8.x API Documentation Consistency Validation (MANDATORY when API changed)

For each changed endpoint, compare API documentation sources (generated OpenAPI descriptions and/or API documentation snippets in code/tests) against `PROJECT_API_DEFINITION`:

1. Method-level text quality:
   - HTTP method/path context is documented correctly
   - Summary and description are equivalent or better than API Definition text
2. Payload text quality:
   - Request field descriptions preserve API Definition semantics and constraints
   - Response field descriptions preserve semantics and do not weaken meaning
3. Error documentation quality:
   - Error code descriptions/status semantics are consistent with API Definition

### 8.x.1 Framework/Native Validation Allowance (IMPORTANT)

When an error is produced by native Kotlin/Spring/Jackson/Bean Validation behavior (not domain business logic),
it is acceptable for documentation/spec examples to use generic `BAD_REQUEST` semantics.

Treat as **PASS (no mismatch)** when ALL of the following are true:
- Failure source is framework/native validation (e.g., Kotlin nullability binding failure, enum parsing failure,
  `@Valid`/`@NotBlank`/`@Size`/other annotation-based validation failure, malformed request body/path/query parameter format)
- There is no custom domain error-mapping logic in the changed implementation for that case
- HTTP status semantics remain correct (typically 400)

Treat as **FAIL (mismatch)** when ANY of the following are true:
- API Definition requires a domain-specific error code for a business-rule failure handled in service/use-case logic
- Implementation documentation weakens or replaces a domain-specific business error with generic `BAD_REQUEST`
- Documentation contradicts API Definition error semantics

Examples:
- ✅ Acceptable generic `BAD_REQUEST`: invalid enum value rejected by framework binding
- ✅ Acceptable generic `BAD_REQUEST`: `@Size(min=1)` violation on request field
- ❌ Not acceptable generic `BAD_REQUEST`: documented domain case like `TEACHER_GROUP_IMMUTABLE` or
  `MEMBER_LIMIT_EXCEEDED` when that rule is business logic and explicitly defined in API Definition

**Acceptance rule: "consistent or better"**
- PASS: Equivalent meaning OR richer detail with no contradiction
- PASS: Generic `BAD_REQUEST` is allowed for framework/native validation-originated failures (per 8.x.1)
- FAIL: Contradiction, omission of key semantics/constraints, or weaker/misleading text

### 8.y Severity Policy for API Documentation Mismatches

- 🔴 **Critical**: Documentation contradicts API Definition semantics (method behavior, payload meaning, or error behavior)
- 🟠 **Major**: Key API Definition semantics/constraints are missing or significantly weaker in implementation docs
- 🟡 **Minor**: Wording/style clarity issues without semantic mismatch
- ℹ️ **No Issue**: Generic `BAD_REQUEST` used for framework/native validation-originated failures (allowed by 8.x.1)
- 🟢 **Positive**: Documentation is more detailed than API Definition while remaining fully consistent

---

## Step 8.5: Data View Compliance (DynamoDB Data Model & Access Patterns)

> **PREREQUISITE**: This step requires `PROJECT_DATA_VIEW`.
> **IF `PROJECT_DATA_VIEW` is EMPTY**: Skip this entire step. Add to the report: "⚠️ Data View document not found — data model and access pattern validation was skipped."

> **Applies when** changes touch any of the following:
> - DynamoDB entities (`@DynamoDbBean`-annotated classes)
> - Repository implementations (e.g. `*RepositoryImpl.kt`, `ddb/` sub-packages)
> - DDB constants (table name, GSI names, attribute names, key prefixes/suffixes)
> - `DynamoDbConfig` / local DDB scaffolding (`LocalDynamoDbConfig`, synthetic key entities used for local table creation)
> - Query/update expressions or new access paths

**IF `PROJECT_DATA_VIEW` is set**: Read the file at `PROJECT_DATA_VIEW` and validate the change against the documented data model and access patterns.

**What to check:**

1. **Table strategy & name**
   - Single-table vs multi-table strategy is respected as defined in the Data View
   - Canonical table name constant matches Data View (e.g., `GROUP_MGMT_TABLE_NAME = "group_mgmt"`)
   - Environment prefix/postfix composition is applied through a single canonical bean (not duplicated in multiple places)

2. **Primary keys (PK/SK)**
   - Partition key and sort key prefixes match Data View conventions (e.g. `G#`, `M#U#`, `M#G#`, `TI#`, `GN#`)
   - Key composition formulas match (e.g., `memberIdKey = "M#{memberId}#{memberType}"`)
   - Polymorphic sort key prefixes do not collide across entity types (e.g. `GN#` for groups vs `TI#` for task items)
   - Key attribute names use the constants defined in the project (no magic strings)

3. **GSIs (Global Secondary Indexes)**
   - GSI count matches Data View (e.g. Data View says 5 GSIs → code/local scaffolding must have 5)
   - For each GSI: PK attribute, SK attribute, and projection type match Data View
   - GSI names match the canonical constants
   - Synthetic "all-GSI" entities used for local table creation (e.g. `KeyEntity` in `LocalDynamoDbConfig`) expose EVERY GSI listed in Data View — a missing GSI causes local-dev tests that exercise that access path to silently fall back to scans or fail

4. **Attributes**
   - Attribute names match Data View (use constants from `DdbConstant` or equivalent)
   - Required attributes (per Data View schema rows) are non-nullable in the entity type; optional attributes are nullable
   - Denormalized fields (e.g. `parentId`, `memberNameLower`, `parentSortKey`) are populated on writes as specified
   - TTL-bearing items (e.g. task items) use `Expirable`/`@DynamoDbConvertedBy(InstantToNumberConverter)` and set the correct attribute

5. **Access patterns**
   - New or changed repository method maps to an access pattern documented in the Data View "Access Patterns Summary" table
   - The query strategy chosen (Query vs GetItem vs Scan) matches the documented strategy
   - If a new access pattern is introduced that is NOT in the Data View, flag it and ask whether the Data View document should be updated first

6. **Transactional semantics**
   - TransactWrite / BatchWrite operations match the atomicity boundaries described in Data View
   - Optimistic locking (`@DynamoDbVersionAttribute`) is used for items that the Data View marks with a `version` attribute
   - Conditional expressions for uniqueness (e.g. `attribute_not_exists(PK)` on GroupKey marker creation) are preserved

### 8.5.1 Severity Policy for Data View Mismatches

- 🔴 **Critical**: Data model change that breaks an access pattern, corrupts key-space (PK/SK prefix collision), or silently drops a GSI relied on by production access paths
- 🟠 **Major**: Attribute/GSI/Access-pattern mismatch vs Data View; magic strings used instead of canonical constants; denormalized field not populated on write; local-dev scaffolding missing a GSI that Data View lists
- 🟡 **Minor**: Naming drift from Data View (e.g. constant present but unused), comment/documentation drift, stylistic inconsistency
- 🟢 **Positive**: Change reduces duplication (single canonical table-name / key-composition bean), adds a GSI that Data View already requires, introduces missing `Auditable`/`Expirable` traits where Data View mandates them

### 8.5.2 Pre-existing vs in-scope findings

When a Data View gap is discovered (e.g., a GSI missing from a synthetic `KeyEntity`) but the reviewed diff does NOT touch the relevant code, report the gap as a **contextual observation out of scope**, not as a finding on this review. Still include it under a `📊 Data View Observations (out of scope)` bullet list in the report so it is not lost.

---

## Step 9: Business Logic & SRS Validation

> **PREREQUISITE**: This step requires `PROJECT_SRS` and optionally `PROJECT_USE_CASES`.
> **IF both `PROJECT_SRS` and `PROJECT_USE_CASES` are EMPTY**: Skip this entire step. Add to the report: "⚠️ SRS and Use Case documents not found — business logic validation was skipped."
> **IF `PROJECT_SRS` is EMPTY but `PROJECT_USE_CASES` is set** (or vice versa): Perform partial validation using whichever document is available. Note the missing document in the report.

**IF `PROJECT_SRS` is set**: When changes touch UseCase classes, validators, event handlers, or repository logic — read the file at `PROJECT_SRS` and validate against its functional requirements.

**IF `PROJECT_USE_CASES` is set**: Also read the file at `PROJECT_USE_CASES` and cross-reference use case specifications.

**What to check:**
- Business rules from the SRS are correctly enforced in use case implementations
- Authorization checks follow the permission matrix defined in the SRS
- State transitions and immutability rules are respected
- Nesting/hierarchy validation rules are implemented (circular reference prevention, etc.)
- Events are published on the correct topics with correct payloads after successful operations
- Consumed events trigger correct cascade behavior
- Error conditions from the SRS error code reference are handled with the correct error codes
- Read full method context — not just diff lines — to understand complete business flow

**Apply 2x severity multiplier** for business logic violations in UseCase classes.

---

## Step 10: Testing Standards

When reviewing test files, validate against established testing patterns.

**Key areas to check:**
- [ ] **Frameworks**: Kotlin Test Framework preferred over JUnit Jupiter. MockK is the primary mocking library (not Mockito, except for simple validator tests).
- [ ] **MockK type erasure pitfall**: Use `match { it is SpecificType }` instead of `any<SpecificType>()` inside `verify {}` — generics are erased at runtime.
- [ ] **Test naming**: Backtick descriptive names (`` `should return X when Y` ``).
- [ ] **Test types**: Controllers → `@ControllerDocumentationTest` + MockMvc. UseCases → `@ExtendWith(MockKExtension::class)`. DynamoDB → `@DdbTest`.
- [ ] **Event tests**: Sealed class exhaustiveness with `require(generatedEvents.size == allConcreteSubclasses.size)`.
- [ ] **Test independence**: No shared mutable state between tests.

> ⚠️ **Anti-false-positive — Controller Test Full Dependency Mocking**: In `@ControllerDocumentationTest` classes, `@MockkBean` declarations for controller dependencies that are **not directly invoked** in that test's scenarios are **NOT** a violation. They are mandatory for Spring application context wiring of the full controller dependency graph. Do **NOT** report these as "unnecessary dependencies" or flag them as a quality issue.

→ See [testing-standards.md](testing-standards.md) for full patterns, import lists, and code examples.

---

## Step 10.5: Lineage Enforcement (ADR-0061)

Run after finding synthesis and verification complete — after Step 4.2 for `--effort high`, Step 4.1 for `--effort medium`, and Step 4.9 for `--effort low` — immediately before Step 11. Findings go in the report's **🔗 Lineage** subsection (Step 13), separate from the other findings sections.

**Resolve the lineage anchor.** Read the ticket's `**Spec**:` slug (spec-linked) or `**Source ADR**:` path (adr-direct) from the diff context, PR body, or the ticket file. If neither anchor is present, record "no lineage anchor found" and skip both checks below.

### 10.5.1 Primary — Code-to-spec alignment (grade-impacting)

Branch on anchor type first:

- **Spec-linked anchor** (`**Spec**:` slug present): read `.scratch/<slug>/spec.md`. **If the file does not exist or has no frontmatter, skip this check entirely** — Group F (Critic) will catch the missing spec; do not escalate here. If resolved, compare the code changes against the spec's acceptance criteria and implementation decisions.
- **ADR-direct anchor** (`**Source ADR**:` path present, no `**Spec**:` slug): read the referenced ADR file from `docs/adr/`. Compare the code changes against the ADR's Decision and Consequences sections.

In both branches, apply the same two-way comparison:
  - Code adds behavior not described → **MAJOR**: "Undocumented scope creep: `<behavior>` not in spec."
  - Code omits required behavior → **MAJOR**: "Incomplete implementation: `<requirement>` specified in spec but not present in code."

These MAJOR findings **count toward the grade** (Step 12) exactly like any other Major finding.

### 10.5.2 Secondary — Spec-to-ADR chain visibility (informational, no grade impact)

- Read the resolved spec's `**Source ADR**:` field.
- If the field is missing, or any listed ADR path does not resolve to an existing file under `docs/adr/` → **MINOR (informational)**: "Spec lacks valid ADR anchor; ask architect to trace this spec to its source decisions."
- This finding is purely informational: it **does not subtract from the grade** (exception to the normal −2 per Minor).
- If the spec was not resolved in 10.5.1 (absent or no frontmatter), skip this check entirely.

---

## Step 11: Categorize Findings

- 🔴 **CRITICAL**: Security vulnerabilities, data loss risks, hardcoded secrets, entity leaking beyond persistence boundary
- 🟠 **MAJOR**: Module boundary violations, missing business rule enforcement, wrong error codes, missing event publishing, architecture violations
- 🟡 **MINOR**: Naming conventions, missing documentation, code style, minor improvements
- ℹ️ **NOTE**: Non-blocking observations and subjective polish; Notes do not affect grade
- 🟢 **POSITIVE**: Excellent implementations, good use of Kotlin idioms, well-structured tests

---

## Step 12: Calculate Grade & Verdict

**Formula:**
- Start: 100 points
- Subtract: 20 per CRITICAL, 10 per MAJOR, 2 per MINOR
- Add: 2 per POSITIVE (max +10)
- Notes do not affect grade
- **Business logic multiplier**: CRITICAL/MAJOR findings in UseCase classes count 2x
- **Lineage (ADR-0061)**: code-to-spec MAJOR findings (Step 10.5.1) count as normal Majors (−10 each). The spec-to-ADR MINOR (Step 10.5.2) is informational and does **not** subtract from the grade.

**Grade scale:**
- A+ (95-100), A (90-94), A- (85-89)
- B+ (80-84), B (75-79), B- (70-74)
- C (60-69), D (50-59), F (0-49)

**Verdict:**
- ✅ **APPROVE**: A+ to A-
- ✅ **APPROVE WITH COMMENTS**: B+ to B
- ⚠️ **REQUEST CHANGES**: B- to C
- ❌ **REJECT**: D to F

---

## Step 13: Generate Report

> ⛔ **NON-OPTIONAL**: This step is mandatory. Once Steps 5–11 analysis is complete, you MUST generate the full report immediately. Do NOT:
> - Ask the user for permission to generate the report
> - Wait for a user prompt before writing findings
> - Stop after summarizing issues without producing the full structured report
> - Produce a free-form report that deviates from the section structure below — **the exact section headings are mandatory**, including `🔎 Build/OpenAPI Verification`, `🧾 API Documentation Consistency Check`, `📊 Data View Compliance Check`, `🔗 PR Context Intake`, and `🔗 Lineage`; omitting any mandatory section is a workflow violation
>
> The report below is the primary deliverable of this skill. Generate it now in your response using the exact structure.

```markdown
## Cline Code Review

### 📄 Documents Used
- SRS: [path or "not found — skipped"]
- API Definition: [path or "not found — skipped"]
- Module View: [path or "not found — skipped"]
- Use Cases: [path or "not found — skipped"]
- Data View: [path or "not found — skipped"]

### Diff Baseline
- **Base ref:** [REVIEW_BASE_REF value or N/A for working-tree]
- **Base ref source:** [pr-base / fallback-default / N/A]
- **Baseline mode:** [merge-base / merge-preview / working-tree]
- **Merge-base SHA:** [output of git merge-base origin/$REVIEW_BASE_REF HEAD or N/A]

### 🔨 Build Status: [SUCCESS / FAILED / WAIVED]

### 🔎 Build/OpenAPI Verification (MANDATORY)
- Build command used: `[exact command or "waived"]`
- Build command compliance: `[PASS / FAIL / WAIVED]`
- Build exit status: `[0 / non-zero / waived]`
- OpenAPI check command: `[exact command or "waived"]`
- OpenAPI verification result: `[VERIFIED / MISSING / WAIVED / UNKNOWN]`
- OpenAPI endpoint coverage: `[VERIFIED / MISSING / NOT_APPLICABLE / WAIVED]`
- Review mode: `[FULL / PARTIAL]`
- If PARTIAL: `Reason + user confirmation text`

### 🧾 API Documentation Consistency Check (MANDATORY)
- Scope reviewed: `[changed endpoints/files reviewed]`
- Method comments consistency vs API Definition: `[PASS / FAIL]`
- Request payload comments consistency vs API Definition: `[PASS / FAIL]`
- Response payload comments consistency vs API Definition: `[PASS / FAIL]`
- Error documentation consistency vs API Definition: `[PASS / FAIL]`
- Framework-validation BAD_REQUEST allowance applied: `[YES / NO]`
- Summary: `[consistent / better / mismatches found]`
- Mismatch list (if any): `[file/path + issue + expected meaning]`

### 📊 Data View Compliance Check (MANDATORY when data model touched)
- Scope reviewed: `[changed DDB entities/repositories/constants/configs or "no DDB changes"]`
- Table strategy & table name alignment: `[PASS / FAIL / N/A]`
- Primary key (PK/SK) alignment: `[PASS / FAIL / N/A]`
- GSI set alignment (count, names, PK/SK, projection): `[PASS / FAIL / N/A]`
- Attribute naming & optionality alignment: `[PASS / FAIL / N/A]`
- Access-pattern mapping to Data View: `[PASS / FAIL / N/A]`
- Transactional/optimistic-locking semantics alignment: `[PASS / FAIL / N/A]`
- Summary: `[aligned / mismatches found / N/A]`
- In-scope mismatches (if any): `[file/path + issue + expected Data View reference]`
- Out-of-scope observations (pre-existing gaps in Data View alignment): `[list or "none"]`

### 🔗 PR Context Intake (MANDATORY status reporting)
- `gh` availability/auth status: `[READY / NOT_READY]`
- PR integration status: `[ENABLED / DISABLED]`
- PR context collected: `[YES / NO]`
- PR integration reason (if disabled): `[reason or N/A]`
- PR: `[number + url + state or N/A]`
- Unresolved threads before review: `[count or N/A]`
- Thread triage: `[X likely addressed / Y still open / Z needs confirmation or N/A]`
- Findings already tracked in PR threads: `[count + references or N/A]`
- Findings not yet tracked in PR discussion: `[count or N/A]`
- Helper artifacts: `[/tmp/code-review-pr-discover.json, /tmp/code-review-pr-triage.json or N/A]`

### 🔴 Critical Issues (X found)
1. **[File]:[Line]** - [Issue]
   - **Fix**: [Solution]
   - **Impact**: [Why it matters]

### 🟠 Major Issues (X found)
1. **[File]:[Line]** - [Issue]
   - **Fix**: [Solution]

### 🟡 Minor Issues (X found)
1. **[File]:[Line]** - [Issue]
   - **Fix**: [Solution]

### ℹ️ Notes (X found) - non-blocking observations, do not affect grade
1. **[File]:[Line]** - [Observation]

### 🟢 Positive Highlights (X found)
1. **[File]** - [What's good]

### 🔍 Candidate Issues (Not Confirmed) — effort = high only; omit section otherwise
> These findings were raised but refuted by adversarial verification. They are excluded from the grade. Include for transparency.
1. **[File]:[Line]** - [Issue] *(Refuted: [reason])*

### 🔗 Lineage (ADR-0061)
- Lineage anchor: `[**Spec**: <slug> / **Source ADR**: <path> / none found — checks skipped]`
- Reference resolved: `[.scratch/<slug>/spec.md (spec-linked) / docs/adr/<path> (adr-direct) / not found or no frontmatter — checks skipped]`
- **Code-to-spec alignment** (grade-impacting; lineage Majors below count −10 each in the grade):
  - Undocumented scope creep (Major): `[file:line + behavior, or "none"]`
  - Incomplete implementation (Major): `[requirement, or "none"]`
- **Spec-to-ADR chain visibility** (informational, no grade impact):
  - Source ADR: `[present + resolves / missing / dangling: <path>]`
  - Finding: `[Minor (informational) — "Spec lacks valid ADR anchor; ask architect to trace this spec to its source decisions." / none]`

---

### ✅ Verdict: [VERDICT] | Grade: [GRADE]

**Summary**: [1-2 sentence executive summary]

### 🔨 Action Items
- [ ] [Specific action with file:line reference]

---

📊 **Review Stats**: X files | +X/-X lines | X issues
```

After presenting report, ask: "Would you like me to help address any of these findings?"

> ⛔ **MANDATORY TRANSITION TO STEP 13.5**: When `PR_INTEGRATION = ENABLED` and `CURRENT_PR_NUMBER` is resolved, you MUST proceed to Step 13.5 immediately after presenting the report. Do NOT end the session, do NOT wait for the user to ask. Silently skipping Step 13.5 when PR integration is available is a workflow violation identical in severity to skipping the build gate.

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

---

## Step 13.6: Task Tracking Offer (always, consent-gated)

After the report (and after Step 13.5 when PR integration is active), ask the user once:

> "Would you like me to create task list items for the remediation action items in this review?"

**IF yes:**
- Call `TaskCreate` for each distinct action item listed in the `🔨 Action Items` section of the report.
- Group related findings into a single task when they share a root cause or file (prefer fewer, more specific tasks over one task per finding).
- Use these field values:
  - `subject`: imperative form — e.g., `Fix make_typed_id ValueError for non-UUID PK in _write.py`
  - `description`: finding text + `file:line` + severity level + recommended fix from the report
  - `activeForm`: `Fixing [short description]` — e.g., `Fixing make_typed_id ValueError`
- After creating all tasks, report the created task IDs at the end of the response.

**IF no:** skip silently.

---

## Step 14: Autonomous Mutating Modes (`--mode autofix` / `review-to-merge`)

> **Mode gate**: This step runs **only** when `REVIEW_MODE_AUTONOMOUS = YES`. In `review` mode the workflow ends after Step 13.6.
>
> ⛔ **Prerequisite (non-bypassable)**: do not begin any RTM phase until the report (Step 13) exists and every read-only gate is resolved (Step 1/1.5 branch+divergence, Step 1.5 PR-context, Step 2 build with `BUILD_STATUS` **not** `FAILED` or `WAIVED`, Step 4.1-RTM + 4.2 verification). See the "RTM/Autofix prerequisite" block under *Non-negotiable execution order*. If `BUILD_STATUS` is `FAILED` or `WAIVED`, report and STOP — do not mutate.

This step inverts the skill's read-only default: it implements fixes, writes tests, commits, and (for `review-to-merge`) pushes and merges. All mutation is gated.

### Design decisions: iteration caps and exit behavior

| Loop | Cap | Exit behavior when cap is hit |
|------|-----|-------------------------------|
| Fix-implementation attempts per finding | **3** | Mark that finding `UNRESOLVED`, revert/leave its code untouched (see recovery rows), continue remaining findings, surface it in the final summary as needing manual attention. Never blocks other fixes. |
| Full-suite debug re-runs after fixes applied | **3** | STOP. Do not commit (if uncommitted); if commits already made, do not push/merge. Report failing tests, the loop's commit SHAs, and recovery options. Terminal stop — no auto-merge, no further retries. |
| Adversarial final-review passes (RTM-6) | **2** | If an accepted Major/Critical is still unaddressed after 2 passes, STOP before push/merge; report the gap. |
| Critic passes over the fix plan (RTM-2) | **fixed 3** (impossible-assumptions, missing-deps/schema-mismatch, test-gap) | Bounded analysis, not a retry loop — run exactly the three, then proceed. No cap-exhaustion state. |

**Exit-state guarantee:** whenever any cap is hit, the terminal state is "report + stop," never push or merge. The only path to push/merge is a fully green suite + a clean adversarial final review + the consent gates below.

### Consent model: BLOCKING gates

- **announced (informational):** the agent prints a banner of what it is about to do; no user reply required. Used for non-mutating progress (e.g. "entering RTM-3, implementing 4 fixes").
- **BLOCKING consent gate (hard gate):** the agent prints the exact git command + target, then STOPS and waits for an explicit user reply before executing. It does not proceed on silence, does not infer consent, and does not batch multiple mutating actions behind one approval. Same force as the Step 1.5 "print verbatim then wait" gate.

| Action | Gate | Default |
|--------|------|---------|
| Commit (RTM-5) | BLOCKING | Explicit confirmation before `git commit`. No auto-proceed. |
| Push (RTM-7) | BLOCKING | Explicit confirmation before `git push`. No auto-proceed. |
| Merge to main (RTM-7) | BLOCKING | Explicit confirmation before merge. No auto-proceed. |

**Operator pre-authorization:** a session may run under "Auto Mode"; the operator MAY pre-authorize specific actions up front (e.g. "autofix and commit without stopping"). When pre-authorized, that gate is satisfied without a per-action pause, but the banner is still announced. **Merge to main is never implicitly auto-authorized** — it always requires a per-action confirmation or an explicit "merge to main without stopping" instruction.

### Phases

**RTM-1 — Status/branch/upstream/scope confirmation.** Confirm `git status`, current branch, upstream tracking, and review scope (reuse Step 1 outputs). If branch/upstream/scope is unclear, default to the safe interpretation — committed scope on the current non-`main` feature branch — and state the assumption. If on `main`, state it immediately, propose a feature branch, and block (do not mutate `main`). **Capture the pre-RTM HEAD SHA** as the rollback anchor for every recovery row.

**Scope-specific handling:**
- **`--scope committed`** (default): fixes are committed as new commits on the feature branch per RTM-5.
- **`--scope working-tree` (or its alias `uncommitted`) + `--mode autofix`**: this is a naturally supported combination. Review the working tree, implement fixes on top of the existing uncommitted work, and commit the reviewed changes **plus** the fixes together at RTM-5 behind the normal BLOCKING consent gate. Do NOT hard-block or ask the user to switch scope — the uncommitted work under review is the intended commit content. The BLOCKING gate at RTM-5 is where the user reviews the exact staged set before confirming; print `git status` there so the staged set is visible.
- **`--scope working-tree` + `--mode review-to-merge`**: the merge step (RTM-7) requires committed-scope semantics and a feature branch. Run review + autofix + commit as above, but before RTM-7 confirm a non-`main` feature branch exists; if only `main` is present, STOP after commit and report (do not merge working-tree fixes straight to `main`).

**RTM-2 — Consolidate fix plan + 3 critic passes.** From the Step 4.1-RTM / 4.2 verified findings, filter to Major/Critical and build an ordered fix plan (each entry: finding id, `file:line`, root cause, proposed fix, regression test to add, dependencies/order). Quarantine any finding that requires a genuine product decision — these are the only stop-for-user items in the loop. Then run the three fixed critic passes over the plan (reuse the Step 4.2 adversarial style, retargeted at the plan): (1) impossible assumptions, (2) missing dependencies / schema or contract mismatches (cross-check `PROJECT_DATA_VIEW` / `PROJECT_API_DEFINITION` / `PROJECT_SRS`), (3) test-coverage gaps. Drop or rewrite plan items the critics refute.

**RTM-3 — Implement fixes + regression tests + selective suite.** Per accepted finding: implement the fix following the relevant standards docs (kotlin/python/testing/security/architecture), one logical change per fix, traceable to a finding id; add or update a regression test that fails before and passes after (3-attempt cap per finding). After all fixes, run the tests via the `testing` skill's selective runner (`--files <changed files from review scope + fix-touched files>`); the testing skill maps those files to their covering tests and **falls back to the full suite automatically when any changed file has zero coverage**, so the safety net is preserved without code-review implementing its own. Loop: if any test fails → debug → re-run, within the 3-rerun cap. Hard rule: do not proceed to commit while the run is red. The user may request a full-suite run explicitly. This is the autonomous fix flow from `~/.claude/CLAUDE.md` (identify Major/Critical → implement → regression tests → run relevant tests → debug to 100% → structured commit), stopping only for genuine product decisions.

**RTM-4 — Summarize changes.** Produce a structured summary: each finding → its fix → its regression test → suite result.

**RTM-5 — Commit (BLOCKING consent gate).** Stage ALL changes per the global git convention (modified files + renames + new files; never a partial set). For `--scope working-tree`/`uncommitted` this stages the reviewed uncommitted work together with the autofixes — that combined set is the intended commit. Print `git status` as part of the BLOCKING banner so the user sees the exact staged set before confirming. Use a structured commit message listing each finding and its fix, with the `Co-Authored-By` trailer. See git-commands.md for the message format. **`autofix` terminates here** — report the commit SHA and summary.

**RTM-6 — Adversarial final review (≤2 passes).** Re-run adversarial verification against the **original** finding list: for each original Critical/Major, confirm it is now actually resolved (`CONFIRMED-FIXED` / `STILL-OPEN` / `REGRESSED`). Also scan the implemented diff for *new* findings (regressions, new security/operational risk). If anything is `STILL-OPEN`, `REGRESSED`, or a new Critical/Major appears → return to RTM-3 (bounded by the cap) or, if the cap is hit, STOP before push and report the gap + commit SHA.

**RTM-7 — Push (BLOCKING gate) then safe merge to main (BLOCKING gate).** Push the feature branch (BLOCKING). Then re-evaluate the merge-safety gate: tests green, RTM-6 clean, branch not behind base (re-fetch base), no conflicts, no-merge-without-consent honored. If safe and confirmed: if a PR exists, merge via the existing PR/repo workflow; otherwise merge the working branch into `main` per the global convention (see git-commands.md). If any safety condition fails → STOP after push, report exactly what blocked the merge, do not force. Record the audit trail: commit SHA, pushed branch, merge result/URL. **`review-to-merge` terminates here.**

---

## Error Handling

- Not in git repository → "Requires git repository"
- On main branch → "Switch to feature branch"
- No changes → "No committed changes to review"
- Git command fails → "Git error: [details]"
- `gh` unavailable or not authenticated → "PR integration unavailable; continuing in non-PR mode"
- No PR for branch → "No PR found for current branch; PR integration skipped unless user provides PR number"
- Non-compliant Gradle command (missing `openapi3`) → "Build command blocked by mandatory OpenAPI gate"
- `build/generated-snippets` exists but `build/api-spec/openapi3.yaml` missing → "OpenAPI artifact verification failed (snippets are insufficient)"

### Mutating-mode error handling (`REVIEW_MODE_AUTONOMOUS = YES`)

- `BUILD_STATUS` is `FAILED` or `WAIVED` at the prerequisite gate → report and STOP; do not start the mutating path (mutation on an unverified baseline is unsafe).
- Suite 3-rerun cap hit, **commits already made** → (1) run `git log <pre-RTM-sha>..HEAD` and report the exact loop SHAs; (2) offer a concrete revert command (`git revert <sha>...` or `git reset --hard <pre-RTM-sha>` with an explicit warning) — do NOT auto-execute; (3) NEVER push/merge. Terminal stop.
- Suite cap hit, **no commit yet** → leave the working tree as-is, report applied vs failing fixes, offer a discard option (`git restore <files>`) — do not auto-discard. NEVER commit.
- Single finding unresolvable in 3 attempts → revert that finding's partial edits (or leave untouched if not yet written), mark `UNRESOLVED`, continue other findings.
- RTM-6 finds an unaddressed accepted finding (`STILL-OPEN`/`REGRESSED`) after the cap → stop before push/merge; report the gap + commit SHA.
- Merge unsafe at RTM-7 (conflicts, protected branch, branch behind base, failing CI on main) → stop after push (branch pushed, mergeable state reported); report why; never force.
- Product-decision finding encountered during the loop → stop and ask the user (the only mandatory blocking question inside the autonomous loop).

---

## PR Integration Safety Rules

- Default mode is read-only for PR operations
- Never publish comments without explicit user confirmation
- Never approve PR without explicit user confirmation
- Never resolve PR threads automatically
- If uncertain where to post inline comment, fall back to draft suggestion and ask user
- In `--mode review-to-merge`, merge is allowed only through the RTM-7 safe-merge gate (tests green, RTM-6 clean, branch not behind base, no conflicts) and still never bypasses the BLOCKING merge consent gate

---

## Reviewer Self-Checklist (before final verdict)

- [ ] `--effort` and `--scope` recorded at top of review
- [ ] **IF `--scope working-tree`**: Steps 1–1.5 skipped; `PR_INTEGRATION = DISABLED` set before Step 2
- [ ] **IF `--scope committed`** (default): Step 1.5 resolved and recorded (`PR_INTEGRATION`, `PR_CONTEXT_COLLECTED`, reason if disabled)
- [ ] **IF `--scope committed` and `gh` ready**: helper-script PR intake (`discover` + `triage`) completed and helper artifacts exist (or explicit user waiver recorded)
- [ ] **IF `--scope committed`** (default): `PR_UNRESOLVED_THREAD_COUNT` recorded (0 is valid, missing is not)
- [ ] Step 2 gate resolved (success+verified OR explicit waiver OR explicit partial-mode approval)
- [ ] **IF `--scope committed`** (default): Build command validated (Gradle commands MUST include `openapi3`)
- [ ] **IF `--scope committed`** (default): Canonical OpenAPI artifact verified at `build/api-spec/openapi3.yaml` (snippets not treated as substitute)
- [ ] `--effort` level recorded; **IF effort = low**: single Explore subagent (Step 4.9) spawned; **IF effort ≥ medium**: 4 fan-out Explore agents A/B/C/D (Step 4.1) spawned and synthesis completed
- [ ] **IF effort = high**: adversarial verifier agents (Step 4.2) run for all Critical/Major findings; REFUTED findings moved to Candidate Issues section
- [ ] API documentation comments validated as consistent-or-better vs API Definition
- [ ] Data View compliance validated when DDB entities / repositories / DDB constants / DDB configs changed (or marked N/A when no DDB changes)
- [ ] Build/OpenAPI verification section included in report
- [ ] Any gate failure/waiver recorded as risk with severity
- [ ] **IF PR integration enabled**: unresolved PR threads were triaged and referenced
- [ ] No worktree created unless `--baseline merge-preview` was explicitly requested
- [ ] **IF PR integration enabled**: Step 13.5 was offered to user after report (PR write actions: comment publishing + approval flow)
- [ ] No PR write action executed without explicit user consent
- [ ] Step 13.6 task tracking offer presented to user after report
- [ ] **IF mutating mode (`autofix`/`review-to-merge`)**: `--mode` was explicitly requested; `REVIEW_MODE_AUTONOMOUS = YES` recorded; effort forced to `high`
- [ ] **IF mutating mode**: on a non-`main` feature branch; all read-only gates resolved and `BUILD_STATUS` not `FAILED`/`WAIVED` before any mutation; pre-RTM HEAD SHA captured
- [ ] **IF mutating mode**: Step 4.1-RTM 4-agent profile used (replacing A/B/C); RTM-2 three critic passes completed; every fix has a regression test; selective suite (testing skill, full-suite fallback on uncovered files) green before commit
- [ ] **IF mutating mode**: commit/push/merge each gated behind a BLOCKING consent gate; no cap-exhaustion state proceeded to push/merge
- [ ] **IF `review-to-merge`**: RTM-6 adversarial final review clean; RTM-7 merge-safety gate evaluated and merge performed only if all conditions green

---

## Usage

See [skill.md](../skill.md) *Common invocations* for the full command table.

Or conversationally:
```
User: /code-review
User: review my uncommitted changes
User: /code-review --effort high --scope committed before I push
```

---

## Reference

### Requirement Documents

Documents are discovered dynamically in Step 0 using `find` commands. The 5 document types used during review are:

| Document Type | Variable | Purpose |
|---------------|----------|---------|
| SRS | `PROJECT_SRS` | Functional requirements, business rules, error codes |
| API Definition | `PROJECT_API_DEFINITION` | API contracts, HTTP methods, paths, error codes, pagination |
| Module View | `PROJECT_MODULE_VIEW` | Module architecture, dependency matrix, use case inventory |
| Use Case Diagrams | `PROJECT_USE_CASES` | Use case specifications with sequence diagrams |
| Data View | `PROJECT_DATA_VIEW` | DynamoDB single-table schema, PK/SK conventions, GSI definitions, access pattern matrix, TTL/versioning rules |

### Standards References

| Topic | Document | Description |
|-------|----------|-------------|
| Kotlin Standards | [kotlin-standards.md](kotlin-standards.md) | Kotlin idioms, vertical-slice architecture, three-tier models, DynamoDB patterns |
| Python Standards | [python-standards.md](python-standards.md) | Python idioms, pydantic v2, DRY patterns, SQL safety, testing |
| Security Patterns | [security-patterns.md](security-patterns.md) | Security review patterns |
| Architecture Patterns | [architecture-patterns.md](architecture-patterns.md) | Module boundary and architecture patterns |
| Testing Standards | [testing-standards.md](testing-standards.md) | Test framework conventions and patterns |

### Modules
- **git-commands.md** — Git command reference for large changesets

### Size Strategy Details

**Token estimation:**
- Small (≤500 lines): ~2K-5K tokens → Full review
- Medium (501-2000 lines): ~10K-30K tokens → Full review
- Large (2000+ lines): ~30K-100K+ tokens → Ask user preference

**Large review options:**
- **Priority**: Fast critical pattern scan (5-7 min)
- **Targeted**: Deep dive on specific area (5-10 min)
- **Multi-pass**: Comprehensive 3-pass review (15-25 min)
