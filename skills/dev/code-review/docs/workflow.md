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

## Gate Invariants

Each gate is a hard stop that enforces one invariant. Multiple enforcement blocks exist by design — an invariant is load-bearing when removing any single block risks silent bypass. This index maps each gate to its invariant and every place it is enforced, so future editors can distinguish load-bearing redundancy from noise.

| Gate | Invariant | Enforced by |
|------|-----------|-------------|
| **Scope** | Scope must be resolved before any repo, PR, build, or diff operation. | Scope Resolution section above; skill.md *Scope Resolution Contract*; each Step 1–2 gate opens with a scope check. |
| **Divergence** (Step 1 / Step 3.5) | When `git status` shows the branch is behind or diverged, the agent must ask the user; never self-decide. | Step 1 "MANDATORY HARD GATE — Branch Divergence Check"; Step 3.5 in the Overview order; ⛔ "NO SELF-DECIDING" block after Step 1. |
| **PR context** (Step 1.5) | When `gh` is available + committed scope, PR intake must complete (or be explicitly waived) before diff commands; the PR Integration State block must appear verbatim in the response. | Step 1.5 opening ⛔ block; Step 1.5.4 "HARD STOP" print-verbatim gate; Step 3 prerequisite list. |
| **Build/OpenAPI** (Step 2) | Build must run (or be waived via `--no-build`) and the OpenAPI artifact verified before diff/stat/log commands. The command runs announced, not confirmed; Gradle commands must include `openapi3`. | Step 2 opening ⛔ block; Step 2.0 flag resolution; Step 2.2 announce-and-run; Step 2.3 command-compliance check; Step 2.5 artifact verification; Step 3 prerequisite list; skill.md *Hard-Stop Rules*. |
| **Diff** | No diff/stat/log/file-inspection command before both the PR-context and build gates are resolved. | "Forbidden before the gates are resolved" block (Step 1.5/2 zone); Step 3 prerequisite block; skill.md *Hard-Stop Rules* diff bullets. Multiple blocks because each marks the boundary from a different angle (what-is-forbidden, what-resolves-it, when-you-may-proceed). |
| **Subagent** (Step 4.9) | All code analysis runs in subagents; never inline in the orchestrator regardless of effort level. | Step 4.9 "MANDATORY TRANSITION" block; ⛔ forbidden list at end of Step 4.9. |
| **Report** (Step 13) | Once analysis is done, the full structured report must be generated immediately; never ask permission; section headings are mandatory. | Step 13 ⛔ "NON-OPTIONAL" block; skill.md Activation Contract step 8. |
| **Mutating consent** (Step 14) | Every commit, push, and merge requires a BLOCKING consent gate. Mutating phases start only after all read-only gates are green and the report is delivered. | workflow-mutating.md Step 14 BLOCKING consent table; RTM prerequisite block (in the Overview); skill.md *Hard-Stop Rules* mutating-mode bullets; skill.md terminal-action table. Multiple blocks because the mutating path is post-report and the read-only gate set must apply unchanged to it. |

---

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

> ⛔ **`--scope committed` with `gh` available: read [workflow-pr.md](workflow-pr.md) *Step 1.5* in full, and satisfy its 1.5.0 Resolution gate (including the verbatim PR Integration State block of 1.5.4) before Step 2.** `--scope working-tree`: skip this step; `PR_INTEGRATION = DISABLED` was set in Step 1.

---

## Step 2: Build Project

> ⛔ **MANDATORY HARD GATE**: You MUST complete this step (or have the user explicitly waive it) BEFORE proceeding to Step 3. Do NOT run any git diff or change analysis commands until this step is resolved.
>
> ⛔ **NO SILENT SKIP**: If this step is not executed, the report MUST state the explicit user waiver text and reason.
>
> ⛔ **ORDER ENFORCEMENT**: Step 2 does not replace Step 1.5. Both gates must be resolved before diff/stat/log commands are allowed.

Build the project before reviewing to ensure generated API specifications are up to date and to validate compilation and tests.

### 2.0 Resolve Build Flags (before detection)

Resolve `--no-build` and `--build-cmd` first; they short-circuit detection and the Unknown-project ask.

| Flags supplied | Behavior |
|---|---|
| `--no-build` (with or without `--build-cmd`) | Skip Steps 2.1–2.5 entirely. Set `BUILD_STATUS = WAIVED`, `OPENAPI_STATUS = WAIVED`, `OPENAPI_ENDPOINT_COVERAGE = WAIVED`, `BUILD_COMMAND_COMPLIANCE = WAIVED`, `REVIEW_MODE = PARTIAL`. Proceed to Step 3. Record in the report: "⚠️ Build gate waived via `--no-build` — tests may be failing or specs may be stale." `--no-build` wins over `--build-cmd`: an explicit skip dominates a supplied command (ADR-0074). |
| `--build-cmd "<cmd>"` alone | Set `BUILD_COMMAND = <cmd>`. Step 2.1 detection still runs, to resolve `PROJECT_TYPE` and `OPENAPI_APPLICABLE` (ADR-0075). |
| neither | Detect in Step 2.1; Step 2.2 resolves `BUILD_COMMAND` from the project-type default. |

The RTM prerequisite gate treats the `--no-build` waiver exactly like a verbal one: mutating modes (`autofix`/`review-to-merge`) stop unless the user re-confirms risk for the mutation specifically.

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

**Unknown**: no descriptor matched. Set `PROJECT_TYPE = Unknown` and `OPENAPI_APPLICABLE = NO` — no JVM descriptor was found that would require the artifact. Step 2.2 resolves what to run.

Set `PROJECT_TYPE` to the detected type (e.g., `Python`, `Gradle`, `Node.js`, `Unknown`).
Set `OPENAPI_APPLICABLE` to `YES` (Gradle/Maven) or `NO` (all others).

### 2.2 Announce-and-Run

Resolve `BUILD_COMMAND`: the `--build-cmd` value when supplied, otherwise the Step 2.1 project-type default.

**When `BUILD_COMMAND` resolves** — **announce-and-run**: print the command in your response text at the **announced** consent level (workflow-mutating.md Step 14 *Consent model*), then proceed to Step 2.3 (ADR-0073).

```
🔨 Running build: `<BUILD_COMMAND>`
```

For non-JVM project types add: "(OpenAPI artifact verification does not apply to this project type.)"

Run `BUILD_COMMAND` in the foreground with the longest timeout the Bash tool allows (600000 ms), never with `run_in_background`: a background gate leaves the review waiting on a child task, so the coordinator sees interim completions instead of the report.

**When `BUILD_COMMAND` does not resolve** — `PROJECT_TYPE = Unknown` and no `--build-cmd`, so there is no command to announce — ask: "No recognized build descriptor found. Please provide the validation command, or explicitly type `skip with risk accepted` to waive this gate." This is the build gate's only remaining ask.

### 2.3 Validate Build Command Compliance (before running)

**Gradle only** — when `PROJECT_TYPE = Gradle`, command validation is mandatory:

- **Required**: command MUST include `openapi3` task
- **Recommended**: `./gradlew clean build openapi3`
- **Explicitly insufficient**: `./gradlew clean build` (missing OpenAPI generation)
- **Explicitly insufficient**: `./gradlew build -x test` (missing OpenAPI generation)

**If the resolved `BUILD_COMMAND` (project default or `--build-cmd`) does NOT include `openapi3`:**
- Do NOT execute the command
- Set `BUILD_COMMAND_COMPLIANCE = FAIL`
- Report that the command is non-compliant with the review gate, naming the missing `openapi3` task
- **Stop the review.** The two recoveries are both re-invocations: `--build-cmd "<corrected command>"`, or `--no-build` to skip the build entirely. Waiving `openapi3` alone while still running the build is out of scope (ADR-0075).

Non-compliant Gradle command execution is forbidden even if suggested earlier in the conversation.

**All other project types** — no compliance constraint on command format. Set `BUILD_COMMAND_COMPLIANCE = PASS` automatically.

Set `BUILD_COMMAND_COMPLIANCE = PASS/FAIL`.

### 2.4 Run Build

**Run the `BUILD_COMMAND` announced in Step 2.2.**

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

**IF the user answers the Step 2.2 Unknown-project ask with `skip with risk accepted`** → Set `BUILD_STATUS = WAIVED`, `OPENAPI_STATUS = WAIVED`, and `REVIEW_MODE = PARTIAL`. Proceed to Step 3. Note in the report: "⚠️ Build gate waived by user with risk accepted — tests may be failing or specs may be stale." (The `--no-build` waiver is set in Step 2.0 and never reaches this step.)

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

> ⛔ **Fan-out dispatch rule** (applies to every fan-out in this file: Step 4.1, the autonomous roster, Step 4.2). Issue all agent calls **in a single message**, in the **foreground** — no `run_in_background`. The calls block and return every finder report inline. Never use `SendMessage` or `notify_when_idle` to wait: `notify_when_idle` works only from the main conversation, and fails with an error when code-review itself runs as a subagent. Do not read the diff, search, or analyze while finders run — the orchestrator's only job in this window is to consume the returned reports. Resume only at Synthesis.

Spawn 4 Explore agents **in parallel**, per the dispatch rule above. Pass each agent:
- The full diff text from Step 4
- All discovered document paths: `PROJECT_SRS`, `PROJECT_API_DEFINITION`, `PROJECT_MODULE_VIEW`, `PROJECT_DATA_VIEW`
- The `--scope` value (so agents know whether Jira commit-message validation applies)
- The ticket/spec/ADR text **verbatim** (quoted or linked), not the implementer's summary or framing of it — a finder reasoning from the implementer's own account of what the ticket requires cannot catch a place where the implementer's account is the thing that's wrong
- Any doubt the implementer holds about their own change, phrased as a candidate finding for the finder to confirm or refute — never resolved by the orchestrator before the finders see it
- The scope rule: every finding carries `in_diff: yes|no` beside its severity — `yes` only when the cited line is added or modified by the diff, `no` when the diff leaves it untouched (pre-existing)

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

Apply the shared **Deep-Module Lens** ([deep-module-lens.md](deep-module-lens.md)).

Prompt:
> You are a high-recall code reviewer (READ-ONLY). Your angles are **Architecture**, **Compliance**, and **Deep-Module Detection**.
>
> First read `~/.claude/skills/code-review/docs/deep-module-lens.md` — it contains the pre-read list, bounded-context rule, and the two deep-module detection scenarios; apply them exactly.
>
> **Architecture & Compliance:**
> - Architecture: module boundary violations, circular dependencies, wrong-layer access (entity leaking beyond repository), field injection anti-patterns, N+1 queries, missing pagination, DynamoDB Limit+FilterExpression misuse
> - API compliance: HTTP method/path/error-code alignment with PROJECT_API_DEFINITION, OpenAPI annotation completeness, API documentation parity (consistent-or-better vs API Definition text). Apply the framework-validation `BAD_REQUEST` allowance and the API-doc severity policy from workflow-compliance.md Steps 8.x.1 and 8.y — read them before grading any error-code or documentation mismatch.
> - Data View compliance: PK/SK prefixes, GSI count/names/projections, attribute naming, access-pattern mapping — validate against PROJECT_DATA_VIEW when DDB entities/repos/configs are changed. Grade per the Data View severity policy and pre-existing-vs-in-scope rule in workflow-compliance.md Steps 8.5.1 and 8.5.2.
> - Cross-file duplication: identify near-identical logic that can be extracted
>
> **Deep-Module Detection:** apply the two scenarios from the shared lens (deep-module-lens.md).
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

After all 4 finder reports return inline:
1. Merge all findings into a single list.
2. Deduplicate: if two agents reported the same issue at the same file:line, keep the higher-severity entry. Finder D (Smell) Notes always lose to any Finder A/B/C finding at the same file:line — drop the Note.
3. Pre-existing: every finding with `in_diff: no` is re-graded MINOR, leaves the grade, and goes to the report's `📌 Pre-existing (outside this diff)` section with the finder's original severity noted. It never reaches a verifier and never blocks approval.
4. Sort: CRITICAL → MAJOR → MINOR → NOTE → POSITIVE.
5. If `--effort medium`: proceed to Step 10.5 (Lineage Enforcement), then Step 11 (Categorize Findings) with this list.
6. If `--effort high`: proceed to Step 4.2 (Adversarial Verification). Finder D Notes are never sent to verifiers.

### Mandatory Pre-Report Verification Protocol

Every Minor/Major/Critical finding must include evidence. Before reporting a finding, verify the actual code path or contract:

1. For missing validation, logic, or checks, trace the dependency chain. Open readers, validators, utilities, and injected services before claiming the logic is absent.
2. For unused imports, dead code, variables, or constants, open the exact file and grep for the symbol in that file.
3. For idiom/style suggestions, open the cited standard and read the full rule including exceptions or `When NOT to apply` clauses.
4. For API, SRS, or Data View contract claims, quote the exact spec line that the code contradicts.
5. Distinguish defects from preferences. If the code works and breaks no rule, report it as Note or drop it.
6. Check the severity itself against Step 11's category definitions. A finding that matches none of the listed MAJOR examples (module boundary violation, missing business rule enforcement, wrong error code, missing event publishing, architecture violation) is not MAJOR — downgrade it to MINOR or NOTE, even when it reads as significant. Parameter order, call-site convention, and similar local-consistency preferences are MINOR at most. So is a refactor proposal (a named field in place of tuple-position, a constant in place of repeated literals, a schema class in place of a dict) that names no input producing a wrong result.
7. The recommended fix is part of the finding. Open the code the fix would change and confirm that applying it keeps every invariant the surrounding code relies on (for example, reading state from a base the code deliberately superseded). A finding whose fix fails that check is reported with a corrected fix, or with no fix.
8. For a CRITICAL or MAJOR claim about concurrency, locking, ordering, or durability, write the failing interleaving as numbered steps (actor A does X, actor B does Y, state Z results) and open the code that brackets it: the enclosing `with`/`try`/transaction scope and the call that returns control. A claim that a lock, transaction or commit happens "before" or "after" something is read off that scope, not inferred from names. When the enclosing scope already orders the steps, drop the finding.

If evidence cannot be produced, drop the finding or downgrade it to Note.

---

## Step 4.1-RTM: Four-Agent Review Profile (mutating modes only)

> `REVIEW_MODE_AUTONOMOUS = YES`: read [workflow-mutating.md](workflow-mutating.md) *Step 4.1-RTM*. Its 5-agent roster replaces the A/B/C/D finders of Step 4.1; Step 4.2 follows.

---

## Step 4.2: Adversarial Verification (effort = high only)

> **Effort gate**: Only runs when `--effort high`. Skip when `--effort low` or `--effort medium`.

For each **CRITICAL or MAJOR** finding from Step 4.1, spawn a targeted Explore agent (up to 4 concurrently, per the Step 4.1 dispatch rule; batch remaining findings if more than 4):

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
> Also check two things: (1) whether the cited line is added or modified by the diff (`git diff` hunks), and (2) whether applying the recommended fix would keep every invariant the surrounding code relies on.
>
> Return one of:
> - `CONFIRMED` — the finding is definitely real; the code has this problem. Add `Corrected fix:` when the recommended fix fails check (2).
> - `PLAUSIBLE` — the finding is likely real but requires runtime or context not visible in static analysis
> - `PRE_EXISTING` — the problem is real but the cited line is outside the diff
> - `REFUTED` — the finding is wrong, already handled, or inapplicable

**Outcome mapping:**
- `CONFIRMED` or `PLAUSIBLE` → include in main report at stated severity
- `PRE_EXISTING` → move to the `📌 Pre-existing (outside this diff)` section at MINOR; exclude from grade calculation
- `REFUTED` → move to `### 🔍 Candidate Issues (Not Confirmed)` section in the report; exclude from grade calculation

> MINOR findings are **not** sent to verifiers (cost vs benefit). They proceed directly to Step 11.

After all verifier agents complete, proceed to Step 10.5 (Lineage Enforcement), then Step 11 (Categorize Findings) with the verified finding list.

---

## Step 4.9: Data Collection Complete — Spawn Review Subagent(s)

> ⛔ **MANDATORY TRANSITION**: All prerequisite data (diff, file contents, commit log) is now collected. For ALL effort levels, code analysis runs in subagents — never inline in the orchestrator. While subagents run, the orchestrator does no review work of its own (see the Step 4.1 dispatch rule).

**IF `--effort low`**: Spawn a single general-purpose Explore subagent. Pass it:
- The complete diff text from Step 4
- All discovered document paths: `PROJECT_SRS`, `PROJECT_API_DEFINITION`, `PROJECT_MODULE_VIEW`, `PROJECT_DATA_VIEW`
- The `--scope` value (so it knows whether Jira commit-message validation applies)
- Pre-read instructions:
  1. Read `~/.claude/skills/improve-codebase-architecture/SKILL.md` — for the deep-module detection lens and deletion test.
  2. Read `~/.claude/skills/codebase-design/SKILL.md` — for the canonical vocabulary: **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**. Use these terms exactly in findings.
  3. Read `~/.claude/skills/codebase-design/DEEPENING.md` — for dependency classification and seam discipline.
  4. Read `~/.claude/skills/code-review/docs/deep-module-lens.md` — the shared deep-module detection scenarios (same as medium/high effort paths).
  5. Read `~/.claude/skills/code-review/docs/smell-baseline.md` — the canonical 12-smell catalogue and binding rules for the maintainability-smells dimension.
- This analysis brief:

> You are a high-recall code reviewer (READ-ONLY). Analyze the diff against all dimensions below and return a unified finding list.
>
> **Commit messages** (committed scope only): check each commit message for Jira ticket reference `[A-Z]+-\d+:` at start — MAJOR if missing.
>
> **Kotlin/language standards**: vertical-slice pattern (UseCase `@Service` with `operator fun invoke()`, thin controllers, constructor injection only); three-tier model (API models → Resources → Entities, no entity leaking beyond repository); `@JsonIgnoreProperties(ignoreUnknown = true)` on request models but NOT response models; Kotlin idioms (`data class` with `val`, extension functions, sealed interfaces, `checkNotNull {}`); custom validators in `validator/` sub-package; centralized `@RestControllerAdvice`.
>
> **Module architecture** (when MODULE_VIEW provided): zero circular dependencies; module boundaries respected per Module View; shared modules have no dependencies on feature modules; cross-module reads go through interfaces.
>
> **Deep-Module Detection**: Apply the two scenarios from `~/.claude/skills/code-review/docs/deep-module-lens.md` (the shared lens used by medium/high-effort finders). Use codebase-design vocabulary (module, interface, depth, seam, adapter, leverage, locality) in all findings.
>
> **API compliance** (when API_DEFINITION provided): HTTP method + path matches spec; request/response fields correct; error codes correct; pagination follows project pattern; OpenAPI annotations present; API documentation semantically consistent-or-better vs API Definition. Apply the framework-validation `BAD_REQUEST` allowance and API-doc severity policy from workflow-compliance.md Steps 8.x.1 and 8.y before grading any error-code or documentation mismatch.
>
> **Data View compliance** (when DATA_VIEW provided, if DDB entities/repos/constants changed): PK/SK prefixes match; GSI count/names/projections match; attribute naming correct; access-pattern mapping to Data View; transactional semantics correct. Grade per the Data View severity policy and pre-existing-vs-in-scope rule in workflow-compliance.md Steps 8.5.1 and 8.5.2.
>
> **Business logic** (when SRS provided, for UseCase/validator/event-handler changes): business rules enforced; authorization correct; state transitions respected; events published correctly. Apply 2x severity multiplier for UseCase findings.
>
> **Testing standards**: Kotlin Test over JUnit; MockK `match {}` vs `any<T>()` pitfall; backtick descriptive names; correct test types per class; event exhaustiveness checks; test independence.
>
> **Maintainability smells** (Fowler ch.3 — always Notes, never grade-affecting): apply the canonical 12-smell catalogue and binding rules from the pre-read `~/.claude/skills/code-review/docs/smell-baseline.md`. Only raise a smell you can name concretely with a specific code location.
>
> For each finding return: `severity` (CRITICAL/MAJOR/MINOR/NOTE/POSITIVE), `file:line`, `description`, `recommended fix` (or `what's good` for POSITIVE). Add `in_diff: yes|no` (`yes` only when the cited line is added or modified by the diff); an `in_diff: no` finding is reported MINOR in the `📌 Pre-existing (outside this diff)` section, outside the grade. Open the code a recommended fix would change and confirm the fix keeps the invariants that code relies on. Prefer omission over false positives.

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

> `--scope committed` with `PR_INTEGRATION = ENABLED`: read [workflow-pr.md](workflow-pr.md) *Step 4.5* and run it before Step 11. `--scope working-tree`: skip.

---

# Compliance Reference (Steps 5–10)

> Steps 5–10 (commit messages, Kotlin and Python standards, module architecture, API definition, Data View 8.5, business logic, testing standards) live in [workflow-compliance.md](workflow-compliance.md). Read it when `--effort low` (Step 4.9 applies it), and read Steps 8.x.1, 8.y, 8.5.1 and 8.5.2 there before grading an API-doc or Data View mismatch. They are NOT orchestrator steps: all effort levels analyze through subagents.

---

# Orchestrator Steps (resume)

> The Compliance Reference (disclosed in workflow-compliance.md) ends here. Steps 10.5 onward are **real orchestrator steps** run by the orchestrator (not subagent reference material), per Step 4.1/4.2/4.9 routing.

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

Copy one verdict string verbatim from this list, chosen by the grade of the confirmed findings. Any confirmed CRITICAL or MAJOR finding caps the verdict at ⚠️ **REQUEST CHANGES**, whatever the grade. With zero confirmed CRITICAL and MAJOR findings the verdict is at least ✅ **APPROVE WITH COMMENTS**, whatever the grade.

---

## Step 13: Generate Report

> ⛔ **NON-OPTIONAL**: This step is mandatory. Once Steps 5–11 analysis is complete, you MUST generate the full report immediately. Do NOT:
> - Ask the user for permission to generate the report
> - Wait for a user prompt before writing findings
> - Stop after summarizing issues without producing the full structured report
> - Produce a free-form report that deviates from the section structure below — **the exact section headings are mandatory**, including `🔎 Build/OpenAPI Verification`, `🧾 API Documentation Consistency Check`, `📊 Data View Compliance Check`, `🔗 PR Context Intake`, and `🔗 Lineage`; omitting any mandatory section is a workflow violation
>
> The report below is the primary deliverable of this skill. Generate it now in your response using the exact structure.
>
> **Citation rule:** every finding and action item names the enclosing function or class in backticks next to `file:line`. `file:line` is valid for this diff only, because the next edit moves it; the code name survives. A reader who copies a finding into a ticket, commit or PR cites the code name, never the line.

> **Compact form (clean review):** when the final finding set has zero Critical and zero Major findings, emit instead: the `🔨 Build Status` line with the build command used and its exit status, the `Review mode` line, one line per Minor/Note finding (severity, `code_name`, file:line, evidence), and the grade and verdict. Skip the Positive-notes narration and every mandatory section whose check was `WAIVED` or `NOT_APPLICABLE`; keep any section that recorded a result (`PR Context Intake` when a PR exists, `Lineage` when it has findings). Any Critical or Major finding restores the full structure below.

```markdown
## Code Review

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

### 🔨 Build Status: [SUCCESS / FAILED / TIMED_OUT / WAIVED]
- Gate summary line: `[the runner's own final summary line, quoted / "n/a (waived)"]`

### 🔎 Build/OpenAPI Verification (MANDATORY)
- Build command used: `[exact command / "waived (--no-build)" / "waived (user)"]`
- Build command source: `[project-type default / --build-cmd / user-supplied (Unknown ask) / N/A]`
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
1. **[File]:[Line]** (`[code_name]`) - [Issue]
   - **Fix**: [Solution]
   - **Impact**: [Why it matters]

### 🟠 Major Issues (X found)
1. **[File]:[Line]** (`[code_name]`) - [Issue]
   - **Fix**: [Solution]

### 🟡 Minor Issues (X found)
1. **[File]:[Line]** (`[code_name]`) - [Issue]
   - **Fix**: [Solution]

### ℹ️ Notes (X found) - non-blocking observations, do not affect grade
1. **[File]:[Line]** (`[code_name]`) - [Observation]

### 🟢 Positive Highlights (X found)
1. **[File]** - [What's good]

### 🔍 Candidate Issues (Not Confirmed) — effort = high only; omit section otherwise
> These findings were raised but refuted by adversarial verification. They are excluded from the grade. Include for transparency.
1. **[File]:[Line]** (`[code_name]`) - [Issue] *(Refuted: [reason])*

### 📌 Pre-existing (outside this diff) — omit section when empty
> Real problems on lines the diff does not touch. Reported MINOR, excluded from the grade, never a reason to withhold approval; the author may file a follow-up.
1. **[File]:[Line]** (`[code_name]`) - [Issue] *(finder severity: [CRITICAL|MAJOR|MINOR]; [fix])*

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
- [ ] [Specific action: `code_name` (function or class) + file:line]

---

📊 **Review Stats**: X files | +X/-X lines | X issues
```

After presenting report, ask: "Would you like me to help address any of these findings?"

> ⛔ **MANDATORY TRANSITION TO STEP 13.5**: When `PR_INTEGRATION = ENABLED` and `CURRENT_PR_NUMBER` is resolved, you MUST proceed to Step 13.5 immediately after presenting the report. Do NOT end the session, do NOT wait for the user to ask. Silently skipping Step 13.5 when PR integration is available is a workflow violation identical in severity to skipping the build gate.

---

## Step 13.5: Conditional Mandatory PR Write Actions (EXPLICIT CONSENT REQUIRED)

> `PR_INTEGRATION = ENABLED` and `CURRENT_PR_NUMBER` resolved: read [workflow-pr.md](workflow-pr.md) *Step 13.5* and run it right after the report; every PR write waits for explicit user consent. Otherwise skip.

---

## Step 14: Autonomous Mutating Modes (`--mode autofix` / `review-to-merge`)

> `REVIEW_MODE_AUTONOMOUS = YES`: read [workflow-mutating.md](workflow-mutating.md) *Step 14* (RTM-1…RTM-7, iteration caps, BLOCKING consent gates, recovery rows) after the report exists and every read-only gate is resolved. `--mode review`: the workflow ends after the report (and Step 13.5 when PR integration is active).

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

- Read [workflow-mutating.md](workflow-mutating.md) *Error Handling (mutating modes)*.

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

- [ ] `--effort`, `--scope`, and any `--no-build` / `--build-cmd` flags recorded at top of review
- [ ] **IF `--scope working-tree`**: Steps 1–1.5 skipped; `PR_INTEGRATION = DISABLED` set before Step 2
- [ ] **IF `--scope committed`** (default): Step 1.5 resolved and recorded (`PR_INTEGRATION`, `PR_CONTEXT_COLLECTED`, reason if disabled)
- [ ] **IF `--scope committed` and `gh` ready**: helper-script PR intake (`discover` + `triage`) completed and helper artifacts exist (or explicit user waiver recorded)
- [ ] **IF `--scope committed`** (default): `PR_UNRESOLVED_THREAD_COUNT` recorded (0 is valid, missing is not)
- [ ] Step 2 gate resolved (success+verified OR `--no-build` waiver OR explicit user waiver OR explicit partial-mode approval)
- [ ] **IF `--scope committed`** (default): Build command validated (Gradle commands MUST include `openapi3`; applies to `--build-cmd` values too)
- [ ] Build command announced in response text before execution, or Unknown-project ask issued when no command could be resolved
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
