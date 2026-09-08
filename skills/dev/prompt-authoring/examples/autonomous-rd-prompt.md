# Example — autonomous research and development prompt

## LOOP example (~25 lines)

```
Establish autonomous iterative inspect/analyze/implement/verify process aiming to diagnose and eliminate a recurring workflow issue.

  0) Check current number of lines in the project's primary log file (e.g. `wc -l /tmp/<app>.log`)
  1) Run the real command: `LOG_LEVEL=DEBUG <app> <subcommand>`
  2) Notice console errors and analyze new log entries
  3) Compare the new evidence against current requirements/spec artifacts and any relevant reference-project notes

  4) Pick the most important issue discovered
  5) Look up the likely root cause in the codebase before changing anything
  6) plan-with-critic (3 rounds) for the fix, including one critic pass for simpler alternatives
  7) Write down the concrete success signal for this pass

  8) Proceed to plan execution
  9) If code changes are in scope: refine existing product requirements with FS-skill
  10) Refine derived software requirements with SRS-skill
  11) Refine use cases and data access patterns with data-view skill
  12) Proceed to implementation execution
  12.1) Apply code-review skill to uncommitted code

  13) Re-run the real command and confirm the observed issue is resolved
  14) Run the project's test command and confirm all relevant tests pass
  15) Update any reusable notes or artifacts that should persist into the next pass
  16) Record any remaining issue as the next loop input
  17) Continue to step 0 (repeat)

Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.
```

### Why this is good

- One opening "Establish autonomous iterative …" line states the goal.
- Single self-repeating numbered loop: step 0 is the baseline, final step returns to 0.
- Spec-first chain is explicit: FS-skill → SRS-skill → data-view skill before implementation, then code-review.
- Skills named inline with round counts: `plan-with-critic (3 rounds)`, `FS-skill`, `SRS-skill`, `data-view skill`, `code-review skill`.
- Real command and real log path embedded as loop steps — not as abstract "verification gates".
- Exactly one stop line — verbatim canonical text, not a bullet list.
- ~25 lines, not ~290.

---

## HELPER example (~12 lines)

```
# Audit and update dependency versions

Review the project's direct dependencies and update any that are outdated or have known vulnerabilities.

  1) Run `<package-manager> outdated` and note all outdated packages
  2) Check changelogs or release notes for breaking changes in major version bumps
  3) Update each dependency, running the test suite after each non-trivial bump
  4) Confirm all tests pass and the application starts cleanly

Stop the process when genuinely product design decisions are required from me, otherwise look up the answers in the current requirements/spec artifacts and the codebase.
```

### Why this is good

- Title + one-sentence mission + ≤5 numbered steps.
- Inline verification: "running the test suite after each bump" and "confirm tests pass".
- Canonical stop line at the end.
- No ceremonial sections. ~12 lines total.
