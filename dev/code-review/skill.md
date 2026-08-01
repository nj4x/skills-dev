---
name: code-review
description: Review pull requests, committed branches, or working-tree changes against project standards, requirements, security patterns, and architecture constraints. Use when reviewing a PR, validating a branch before push, checking uncommitted changes, or producing approve/request-changes feedback.
---

# Code Review Skill

Review code changes against project standards, security patterns, requirements, and architecture constraints. The default review policy is committed branch changes against the PR's base branch (default `origin/main`) using the merge-base (three-dot) view; working-tree review is available only when explicitly requested or selected after scope confirmation.

## Parameters

| Parameter | Values | Default | Effect |
|-----------|--------|---------|--------|
| `--effort` | `low`, `medium`, `high` | `high` | Controls analysis depth: `low` = single inline pass, `medium` = 3 parallel Explore agents, `high` = fan-out + adversarial verifier per Critical/Major finding |
| `--scope` | `committed`, `working-tree` | `committed` policy, confirm if omitted | `committed` reviews branch commits against the PR base branch (merge-base / three-dot view); `working-tree` reviews uncommitted local changes via `git diff HEAD` |
| `--baseline` | `merge-base`, `merge-preview` | `merge-base` | `merge-base` (default) diffs `origin/<base>...HEAD` to match the GitHub PR view; `merge-preview` (documented follow-up, not yet wired) would merge the base branch in a disposable worktree to surface integration conflicts |
| `--mode` | `review`, `autofix`, `review-to-merge` | `review` | `review` = read-only review + report (current behavior, no mutation). `autofix` = review, then autonomously implement Major/Critical fixes + regression tests, run the testing skill's selective suite to green (full-suite fallback on uncovered files), and commit; STOPS after commit. `review-to-merge` = everything `autofix` does, then push and (if safe) merge the working branch into main. Both mutating modes force `--effort high` semantics, require a non-`main` feature branch, and gate commit/push/merge behind BLOCKING consent (see Mutating-Mode Contract). Three distinct values, **no synonyms** — an unrecognized value is not guessed; the skill lists the three and asks. |

**Common invocations:**

| Command | Behavior |
|---------|----------|
| `/code-review` | Fan-out + adversarial verify, **committed** scope (confirm if ambiguous), merge-base diff |
| `/code-review --scope working-tree` | Fan-out + adversarial verify, working-tree diff, PR gate auto-disabled |
| `/code-review --effort medium` | 3 fan-out agents (no adversarial verify), committed scope |
| `/code-review --effort medium --scope working-tree` | 3 fan-out agents, working-tree diff |
| `/code-review --effort low --scope committed` | Single-pass inline, committed scope, all hard gates active |
| `/code-review --mode autofix` | Review, then autonomously fix Major/Critical, add regression tests, run selective suite to green (full-suite fallback on uncovered files), commit (BLOCKING). Stops after commit. |
| `/code-review --mode review-to-merge` | `autofix` + push (BLOCKING) + safe merge to main (BLOCKING). |
| `/code-review --mode review-to-merge --scope committed` | Full autonomous review-to-merge on committed branch scope, all gates active. |

---

## Mutating-Mode Contract (`--mode autofix` | `review-to-merge`)

The default `--mode review` is **read-only** — it reviews and reports, never mutating the repo. The `autofix` and `review-to-merge` modes invert that default: they implement fixes, write tests, commit, and (for `review-to-merge`) push and merge. This inversion is strictly opt-in and gated. See [workflow.md](docs/workflow.md) **Step 14** for the full RTM-1…RTM-7 phase spec, iteration caps, consent definitions, and recovery rows.

### Terminal-action table (authoritative)

| Mode | Review | Implement fixes | Regression tests | Test run¹ | Commit | Push | Merge | Terminal action |
|------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| `review` *(default)* | yes | no | no | no | no | no | no | Report delivered. No mutation. |
| `autofix` | yes | yes | yes | yes | yes (BLOCKING) | no | no | Stops after commit; reports SHA + summary. |
| `review-to-merge` | yes | yes | yes | yes | yes (BLOCKING) | yes (BLOCKING) | yes if safe (BLOCKING) | Stops after merge, or after push if merge unsafe, or earlier at any failed gate. |

¹ **Test run** = the `testing` skill's selective runner over the changed files (review scope + fix-touched files), which falls back to the full suite automatically when any changed file has zero coverage. The user may request a full-suite run explicitly.

`review` is byte-for-byte unchanged. The mutating phases run **only after** the standard read-only review report (Phase 4) is delivered, so the read-only deliverable always exists even in a mutating run.

### Consent definitions

- **announced (informational):** the agent prints a banner of what it is about to do; no user reply required. Used for non-mutating progress.
- **BLOCKING consent gate (hard gate):** the agent prints the exact git command + target, then STOPS and waits for an explicit user reply before executing. It does not proceed on silence, does not infer consent, and does not batch multiple mutating actions behind one approval — same force as the Step 1.5 print-verbatim-then-wait gate. An operator may pre-authorize specific actions up front (e.g. "autofix and commit without stopping"); merge-to-main is **never** implicitly pre-authorized.

---

## Scope Resolution Contract

Resolve scope before any repo gate, PR gate, build gate, diff retrieval, or review analysis.

1. If `--scope committed` or `--scope working-tree` is supplied, use it.
2. If the user explicitly says `uncommitted`, `working tree`, `working-tree`, `staged`, `unstaged`, `local changes`, `my diff`, or `pending changes`, use `working-tree`.
3. If the user explicitly says `committed`, `branch`, `commits`, `before push`, `ready to push`, `PR`, or `pull request`, use `committed`.
4. For ambiguous requests, including bare `/code-review`, ask the user to choose scope before starting review work. Offer `committed` as the default option.

## Activation Contract

After activation:

1. Parse `--effort` and resolve or confirm `--scope`.
1a. Parse `--mode` (default `review`). If `review`, follow the read-only contract below unchanged. If `autofix` or `review-to-merge`: force `--effort high` semantics, confirm a non-`main` feature branch and committed-scope semantics first, run the standard read-only review through the report, then execute the Autonomous Mutating Phases (workflow.md Step 14, RTM-1…RTM-7) **after** the report. An unrecognized `--mode` value is not guessed — list the three valid values and ask.
2. Discover requirement and architecture documents: SRS, API Definition, Module View, Use Cases, and Data View.
3. For `committed` scope: verify git repo and valid `HEAD`, resolve `REVIEW_BASE_REF` from the PR base branch (`baseRefName`, fallback `main`) before fetching, fetch `origin/$REVIEW_BASE_REF` and the current branch, handle branch divergence by asking the user, run PR context intake when `gh` is available, and print the PR Integration State block verbatim (Step 1.5.4) before any diff commands.
4. For `working-tree` scope: verify git repo and valid `HEAD`; skip fetch, branch divergence, PR gates, and committed-branch comparison.
5. Resolve the build/OpenAPI gate before diff analysis unless the user explicitly waives it with risk accepted. Auto-detect project type and ask user for build confirmation before running (Step 2.1-2.2): run `for f in build.gradle build.gradle.kts pom.xml pyproject.toml setup.py package.json Cargo.toml go.mod; do [ -f "$f" ] && echo "$f"; done`, present the detected type and default command, and wait for user confirmation; do not silently execute the build.
6. Run build/validation only after user confirmation or a user-provided build command; set `OPENAPI_APPLICABLE = YES` for Gradle/Maven only. If `OPENAPI_APPLICABLE = YES`, verify canonical OpenAPI artifact at `build/api-spec/openapi3.yaml`; on build timeout use `find build -name "openapi3.yaml"` to check; do not use `sleep` and do not use `ls` on a hardcoded path. If `OPENAPI_APPLICABLE = NO`, set `OPENAPI_STATUS = NOT_APPLICABLE`. Then retrieve stats and diff by scope: `origin/<base>...HEAD` (merge-base, three-dot; `<base>` discovered from the PR) for committed scope, `HEAD` for working-tree scope.
7. Review according to effort level. For ALL effort levels, analysis runs in subagents — never inline. For `low`, spawn a single Explore subagent with all review angles merged into one prompt (Step 4.9 in workflow.md). For `medium` or `high`, spawn 4 parallel Explore agents: Finder A (Correctness/Security), Finder B (Architecture/Compliance), Finder C (Quality/Standards), and Finder D (Maintainability Smells) — see Step 4.1 in workflow.md. For `high`, adversarially verify every Critical/Major finding (Step 4.2 in workflow.md) before including it in the grade. Finder D Notes are never sent to verifiers.
7.5. **Lineage enforcement (ADR-0061).** After the standard review passes complete, run these two additional checks. Append findings in a **Lineage** subsection of the report (step 8), separate from other findings.

   **Primary — Code-to-spec alignment (grade-impacting):**
   - Retrieve the ticket's `**Spec**:` slug (spec-linked) or `**Source ADR**:` path (adr-direct) from the diff context or PR description.
   - Resolve the spec: read `.scratch/<slug>/spec.md`. If the file does not exist or has no frontmatter, skip this check — Group F (Critic) will catch the missing frontmatter.
   - Compare code changes against the spec's acceptance criteria and implementation decisions:
     - Code adds behavior not described in the spec: **Major** finding — "Undocumented scope creep: `<behavior>` not in spec."
     - Code omits behavior that the spec explicitly requires: **Major** finding — "Incomplete implementation: `<requirement>` specified in spec but not present in code."
   - For adr-direct tickets (no spec): compare code changes against the ADR's decision and consequences section using the same logic.

   **Secondary — Spec-to-ADR chain visibility (informational, no grade impact):**
   - Read the spec's `**Source ADR**:` field (if the spec was resolved above).
   - If the field is missing or any listed ADR path does not resolve to an existing file under `docs/adr/`: **Minor** finding — "Spec lacks valid ADR anchor; ask architect to trace this spec to its source decisions."
   - If the spec does not exist or has no frontmatter: skip this check.

8. Generate the structured report (Step 13) with severity, evidence, grade, PR context status, build/OpenAPI status, and action items. Include a **Lineage** subsection after the standard findings, listing any code-to-spec or spec-to-ADR findings from step 7.5.
9. If PR integration is enabled, proceed to PR write actions (Step 13.5) and offer PR comments or approval only after explicit user consent.
10. Offer task tracking after the report (Step 13.6).

## Hard-Stop Rules

- Do not run diff/stat/log commands before scope is resolved and the required gates for that scope are complete.
- Do not run `git diff`, `git diff --stat`, or `git log origin/<base>..HEAD` before the build/OpenAPI gate is complete or explicitly waived.
- Do not treat `gh pr view --comments` as a replacement for unresolved review-thread intake.
- Use the merge-base (three-dot) diff `origin/<base>...HEAD` as the primary committed-scope review baseline so the diff matches the GitHub PR Files-changed view. Do not use the two-dot `origin/<base> HEAD` form as the primary review diff: it absorbs target-branch commits added after divergence and inflates the diff.
- Do not create or merge review worktrees for the default `merge-base` baseline; that review is repo-local and non-worktree. Worktree-based merge preview is allowed only under `--baseline merge-preview` (or explicit user request) and must use a unique `/tmp` path, treat merge conflicts as findings, and guarantee `git worktree remove --force` + `git worktree prune` cleanup on success and failure.
- Do not publish PR comments, approve PRs, or resolve PR threads without explicit user consent.
- Every Minor/Major/Critical finding must include verification evidence: dependency chain traced, actual file opened, relevant standard exception checked, or exact spec line quoted. Otherwise downgrade to Note or drop it.
- "Works but could be nicer" is a Note, not a Minor.
- Mutating modes (`autofix`/`review-to-merge`) are never the default and must be explicitly requested via `--mode`. They never replace or skip any read-only gate: the Step 1/1.5 branch+divergence gate, the Step 1.5 PR-context gate, and the Step 2 build/OpenAPI gate MUST all be resolved before any mutation. The mutating path does **not** start if `BUILD_STATUS` is `FAILED` or `WAIVED` (mutation on an unverified baseline is a safety violation) unless the user explicitly re-confirms risk for the mutation specifically.
- In mutating modes, every commit, push, and merge is a **BLOCKING consent gate** (print exact command, stop, wait for explicit reply). Never commit, push, or merge while any relevant test is failing. Never commit fixes directly to `main` — require a feature branch first. Merge to `main` only when tests are green, the adversarial final review (RTM-6) is clean of unfixed Critical/Major, the branch is not behind base, and there are no conflicts; otherwise STOP and report. Merge inherits the existing no-merge-without-consent rule.
- In mutating modes, any iteration cap exhausted (fix attempts, suite debug re-runs, final-review passes) is a terminal stop — report state and recovery options; never auto-push or auto-merge from a cap-exhaustion state.

---

## Quick Reference

### Review Categories

| Category | Focus | Severity Multiplier |
|----------|-------|-------------------|
| 🔴 **Critical** | Security, data loss, secrets | -20 points each |
| 🟠 **Major** | Architecture violations, business logic | -10 points each |
| 🟡 **Minor** | Style, naming, documentation | -2 points each |
| 🟢 **Positive** | Good implementations, idioms | +2 points each (max +10) |

### Size Classification

| Size | Files | Lines | Review Strategy |
|------|-------|-------|----------------|
| **Small** | ≤10 | ≤500 | Full review |
| **Medium** | 11-30 | 501-2000 | Full review |
| **Large** | 30+ | 2000+ | User preference |

### Grade Scale

| Grade | Score | Verdict |
|-------|-------|---------|
| A+ | 95-100 | ✅ APPROVE |
| A | 90-94 | ✅ APPROVE |
| A- | 85-89 | ✅ APPROVE |
| B+ | 80-84 | ✅ APPROVE WITH COMMENTS |
| B | 75-79 | ✅ APPROVE WITH COMMENTS |
| B- | 70-74 | ⚠️ REQUEST CHANGES |
| C | 60-69 | ⚠️ REQUEST CHANGES |
| D | 50-59 | ❌ REJECT |
| F | 0-49 | ❌ REJECT |

---

## Reference Documentation

For detailed guidelines, see the following documents:

| Topic | Document | Description |
|-------|----------|-------------|
| Main Workflow | [workflow.md](docs/workflow.md) | Complete step-by-step review process |
| Security Patterns | [security-patterns.md](docs/security-patterns.md) | Hardcoded secrets, injection risks, CORS issues |
| Architecture Patterns | [architecture-patterns.md](docs/architecture-patterns.md) | Field injection, business logic in controllers, entity exposure |
| Kotlin Standards | [kotlin-standards.md](docs/kotlin-standards.md) | Vertical slice pattern, three-tier model, validation patterns, Data View alignment |
| Python Standards | [python-standards.md](docs/python-standards.md) | DRY, pydantic v2, psycopg2 cursor/row/error/batch patterns, type hints, testing |
| Testing Standards | [testing-standards.md](docs/testing-standards.md) | Kotlin Test Framework, MockK usage, test independence |
| Git Commands | [git-commands.md](docs/git-commands.md) | Git command reference and best practices |
| Maintainability Smells | [smell-baseline.md](docs/smell-baseline.md) | Fowler ch.3 12-smell vocabulary; reported as Notes only (no grade impact) |
