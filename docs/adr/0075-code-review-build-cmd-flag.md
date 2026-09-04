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

For Gradle projects, validate that the supplied command includes `openapi3` before execution (Step 2.3). If non-compliant, refuse to run and ask the user to fix the command or explicitly waive the gate.

## Rationale

**Preserves customization path.** Without this flag, users with non-standard builds must use `--no-build` and build manually, adding friction.

**Compliance check still applies.** Gradle's `openapi3` requirement is not relaxed for custom commands; the validation in Step 2.3 catches gaps.

**Explicit and greppable.** The flag makes custom build choices auditable in review invocations and compatible with scripted/automated reviews.

## Consequences

- `--build-cmd` is added as a first-class parameter.
- When supplied, it overrides the project-type default detected in Step 2.1.
- Gradle compliance check (Step 2.3) validates all supplied commands, not just defaults.
- Non-compliant Gradle commands are refused; user must fix or waive with `--no-build`.
- All other validation steps (build success, timeout handling, artifact verification) proceed as usual.
