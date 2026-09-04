---
lineage-rules: exempt
---

# ADR-0075: Code Review `--build-cmd` Flag

**Status:** Decided  
**Date:** 2026-09-03  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

The skill detects project type and defaults to a standard build command (e.g., `./gradlew clean build openapi3` for Gradle). Some projects require a non-standard build command (e.g., a monorepo submodule, a custom build step, or a wrapper script).

With the Step 2.2 confirmation prompt removed (ADR 0073), there is no interactive opportunity to supply a custom command. Adding `--build-cmd` restores this capability as an explicit flag.

## Decision

Add `--build-cmd "<cmd>"` as a recognized flag to the code-review skill. When supplied, override the detected default and run the supplied command instead.

For Unknown projects (no recognized build descriptor), treat `--build-cmd` as providing the command to run — skip the Step 2.2 prompt entirely and proceed to Step 2.3 validation.

For Gradle projects, validate that the supplied command includes `openapi3` before execution (Step 2.3). If non-compliant, refuse to run and fail fast — the skill exits with a diagnostic; the user must re-invoke with a corrected `--build-cmd` or use `--no-build` to skip the build entirely.

## Rationale

**Preserves customization path.** Without this flag, users with non-standard builds must use `--no-build` and build manually, adding friction.

**Compliance check still applies.** Gradle's `openapi3` requirement is not relaxed for custom commands; the validation in Step 2.3 catches gaps.

**Explicit and greppable.** The flag makes custom build choices auditable in review invocations and compatible with scripted/automated reviews.

## Consequences

- `--build-cmd` is added as a first-class parameter.
- When supplied, it overrides the project-type default detected in Step 2.1.
- For Unknown projects, `--build-cmd` eliminates the Step 2.2 prompt (user provided a command; no guess needed).
- Gradle compliance check (Step 2.3) validates all supplied commands, not just defaults.
- Non-compliant Gradle commands are refused with a diagnostic; user must re-invoke with a corrected `--build-cmd` or use `--no-build` to skip the build.
- **Partial waiver (skip only the openapi3 requirement while running the build) is out of scope for this ADR** — deferred for future consideration if a use case for partial waiver emerges and compliance policy permits it.
- When both `--no-build` and `--build-cmd` are supplied, `--no-build` takes precedence; the build is skipped entirely (see ADR-0074).
- All other validation steps (build success, timeout handling, artifact verification) proceed as usual.
