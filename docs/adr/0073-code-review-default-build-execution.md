---
lineage-rules: exempt
---

# ADR-0073: Code Review Default Build Execution

**Status:** Decided  
**Date:** 2026-09-03  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

The `code-review` skill Step 2 (Build Gate) currently asks the user for confirmation before running the detected build command. This prompt is issued even when a sensible default exists (e.g., `./gradlew clean build openapi3` for Gradle projects), forcing interactive approval on every review that runs a build.

For reviews that run many times per session or as part of an automated pipeline, the confirmation step creates friction without adding safety: the default command is already determined by the project's known structure, and build failures are caught downstream (fail-forward to partial-mode review or blocked mutation).

## Decision

Change Step 2.2 to skip the confirmation prompt when a default build command is detected. Instead, announce the command about to run (informational banner, no reply required) and execute it.

Preserve the ask for Unknown projects (no recognized build descriptor) — there is no default to run, and guessing a build command is worse than asking.

## Rationale

**Reduces friction on the critical path.** Prompt removal speeds reviews without sacrificing safety: build failures still generate Critical findings and block mutation; timeouts still ask for re-run/partial/stop; and Gradle compliance checks still validate the command before execution.

**Preserves control.** The flag `--no-build` waives the gate; the flag `--build-cmd` supplies a custom command. Both remain low-friction alternatives to the prompt.

**Maintains ask for Unknown.** When no descriptor exists, asking is the only safe path; we cannot default to nothing.

## Consequences

- Step 2.2 no longer blocks on user confirmation for detected project types.
- Unknown projects still prompt (no default exists).
- Build failures, timeouts, and compliance violations still trigger interactive asks (Step 2.4).
- Announced command banner before execution allows users to spot unexpected commands before they run.
