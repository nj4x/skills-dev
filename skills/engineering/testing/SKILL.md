---
name: testing
description: Use when running tests or committing changes. Use when the user says "run tests", "run the suite", "commit this", or asks which tests cover a changed file.
---

After code changes, run lint and the tests covering the change (selective runner below). Run the full suite when the runner falls back to it, when no changed-file list is given, or when the user asks.

**Reading results.** Pass/fail comes from the runner's own summary line (pytest's final `N passed` / `N failed` line), read in full. Run the test command unpiped: a pipe (`| head`, `| tail`) returns the last command's exit code, not the runner's, and can cut off the summary. Start a suite expected to exceed two minutes with `run_in_background` and read its summary when it completes — a report of "green" quotes that summary line. Lint and check commands must show their own exit status: chain `&& echo OK` so a proxy that compresses or truncates output cannot turn an empty result into an unverified "clean".

When committing, run `git status` first and stage every file this change created, modified, or renamed — new files and renames included — by name. Leave changes you did not make unstaged and tell the user they are there. Before `git add` on a file, read `git diff <file>`: a file holding hunks you did not write (another ticket's edits) is staged by hunk with `git add -p`; after staging, `git diff --cached` shows only your hunks.

Use real test IDs, real requirement IDs, and real implementations; wire dependencies through the app-level factory interface rather than concrete providers.

## Selective runner

When code-review or the user provides changed files, run only the tests covering those files instead of the full suite.

**Input:**
- `--files <path>...` — explicit source file list
- `--scope committed` (committed but unpushed), `--scope uncommitted` (unstaged changes), or `--scope all` (both)
- No args — run the full suite as usual

**Docs-only changes:** drop documentation files — Markdown, ADRs, requirements, specs — from the changed set before mapping; no test covers them, so they never count as uncovered. If nothing remains, report "no code changed" and run lint only.

**Repo mapper first:** when the repo ships a covering-tests script (its AGENTS.md or testing doc names it), run it instead of the mapping below: it prints the tests to run, and a non-zero exit with `uncovered:` notes triggers the full-suite fallback. Broad `rg` mapping over-matches hub modules (many tests import them).

**Mapping (ripgrep first, search-codebase second, path-based fallback):** for each changed source file —
1. `rg -l` the tests directory for module symbols from the changed file; pair import paths with bare class names to avoid over-matches; add any hits to the run set — including any matches found under the language's integration directory (`tests/integration/`, `integration/`, `src/test/integration/`). When ripgrep finds nothing, query the `search-codebase` skill for tests that reference the file's symbols.
2. If none, apply the `refactor-tests` mirroring convention to compute the expected test path and add it if it exists.
3. If still none, check the integration directory for a file with the same name and add it if it exists.
4. If still none, mark the file uncovered.

**Fallback:** if any changed file is uncovered, run the full suite as a safety net and report which files were uncovered. Otherwise run only the selected subset.

**Report before executing:** list the selected files, list the tests that will run, and note if the full suite was triggered by uncovered files.
