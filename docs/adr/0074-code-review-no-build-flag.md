---
lineage-rules: exempt
---

# ADR-0074: Code Review `--no-build` Flag

**Status:** Decided  
**Date:** 2026-09-03  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

Users may want to skip the Step 2 build gate for several reasons: the build is known to be broken, the changes are review-only (no build/runtime impact), or the codebase requires external setup. The skill currently supports this via "skip with risk accepted" wording in the Step 2.2 prompt, which sets `BUILD_STATUS = WAIVED` and forces `REVIEW_MODE = PARTIAL`.

Adding an explicit `--no-build` flag makes the intent clear at invocation time and eliminates the need for interactive waiver text.

## Decision

Add `--no-build` as a recognized flag to the code-review skill. When supplied, set `BUILD_STATUS = WAIVED`, `OPENAPI_STATUS = WAIVED`, and `REVIEW_MODE = PARTIAL` directly, without prompting. Step 2 is skipped; proceed to Step 3 (diff retrieval and analysis).

Treat `--no-build` as explicit risk acceptance equivalent to the existing verbal waiver. It blocks `autofix` and `review-to-merge` modes at the RTM prerequisite gate unless the user explicitly re-confirms risk for the mutation.

## Rationale

**Explicit > implicit.** A flag at invocation makes the user's intent clear and auditable; it avoids the back-and-forth of a prompt followed by "skip with risk accepted" text entry.

**Reuses existing state.** `BUILD_STATUS = WAIVED` already exists and integrates with mutation gates. No new state machinery required; the flag is just a shorter path to the same outcome.

**Applies to all project types.** Unlike `--build-cmd`, `--no-build` is not Gradle-specific and makes sense for any review that does not need a build.

## Consequences

- `--no-build` flag is added as a first-class parameter alongside `--effort`, `--scope`, and `--mode`.
- Step 2 does not execute when `--no-build` is supplied; no build command is run.
- `BUILD_STATUS` is set to `WAIVED`; the report notes the flag and suppresses the usual "user said skip with risk accepted" text.
- When both `--no-build` and `--build-cmd` are supplied, `--no-build` takes precedence (skip the build entirely); this reflects the user's explicit intent to skip taking priority over any supplied command.
- Mutation modes (`autofix`/`review-to-merge`) still require explicit risk re-confirmation at the RTM prerequisite gate if `BUILD_STATUS = WAIVED`.
