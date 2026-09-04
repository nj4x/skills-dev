---
lineage-rules: exempt
---

# ADR-0073: Code Review Default Build Execution

**Status:** Decided  
**Date:** 2026-09-03  
**Source SRS**: none (lineage exempt; requirements corpus does not exist yet — retrofit tracked in ADR-0065)

## Context

The `code-review` skill Step 2 (Build Gate) currently asks the user for confirmation before running the detected build command. This prompt is issued even when a sensible default exists (e.g., `./gradlew clean build openapi3` for Gradle projects), forcing interactive approval on every review that runs a build.

For reviews that run many times per session or as part of a CI-triggered review gate (where humans are monitoring), the confirmation step creates friction without adding safety: the default command is already determined by the project's known structure, and build failures are caught downstream (fail-forward to partial-mode review or blocked mutation).

## Decision

Change Step 2.2 to skip the confirmation prompt when a default build command is detected. Instead, announce the command about to run (informational banner, no reply required) and execute it.

Preserve the ask for Unknown projects (no recognized build descriptor) — there is no default to run, and guessing a build command is worse than asking.

## Rationale

**Reduces friction on the critical path.** Prompt removal speeds reviews without sacrificing safety: build failures still generate Critical findings and block mutation; timeouts still ask for re-run/partial/stop; and Gradle compliance checks still validate the command before execution.

**Preserves control.** The flag `--no-build` waives the gate; the flag `--build-cmd` supplies a custom command (see ADR-0074, ADR-0075). Both provide low-friction alternatives to the prompt.

**Maintains ask for Unknown.** When no descriptor exists, asking is the only safe path; we cannot default to nothing.

## Consequences

- Step 2.2 no longer blocks on user confirmation for detected project types.
- Unknown projects still prompt, unless `--build-cmd` or `--no-build` is supplied (user-specified commands skip the detection/ask path; `--no-build` skips Step 2 entirely per ADR-0074).
- Build failures, timeouts, and compliance violations still trigger interactive asks (Step 2.4).
- Announced command banner before execution allows users to spot commands; the banner is informational and does not impose a guaranteed abort window. External interruption (e.g., Ctrl-C in interactive terminal sessions) may abort before execution, but is not reliably available in all CI environments.
- The interactive custom-command path (previously available at the Step 2.2 prompt) is removed; users who need a non-default command must now supply `--build-cmd` at invocation time (see ADR-0075).
- **Not applicable to fully unattended automation or CI without interactive terminal.** This ADR assumes human-monitored interactive sessions or CI pipelines with human access to logs. Fully dark, unattended automation is out of scope; use `--build-cmd` to pre-specify the command and rely on Step 2.4 fail-forward. CI users without interactive terminal access should pre-specify intent with `--no-build` or `--build-cmd` rather than relying on interactive abort.
