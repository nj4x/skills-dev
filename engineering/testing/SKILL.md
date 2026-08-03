---
name: testing
description: Use when running tests or committing changes. Use when the user says "run tests", "run the suite", "commit this", or asks which tests cover a changed file.
---

Always run the full test suite AND lint after code changes.

When committing, run `git status` first and stage ALL changes — modified files alongside renames and new files — before creating the commit.

Use real test IDs, real requirement IDs, and real implementations; wire dependencies through the app-level factory interface rather than concrete providers.

## Selective runner

When code-review or the user provides changed files, run only the tests covering those files instead of the full suite.

**Input:**
- `--files <path>...` — explicit source file list
- `--scope committed` (committed but unpushed), `--scope uncommitted` (unstaged changes), or `--scope all` (both)
- No args — run the full suite as usual

**Mapping (search-codebase first, path-based fallback):** for each changed source file —
1. Query the `search-codebase` skill for tests that import or reference symbols from that file; add any hits to the run set — including any matches found under the language's integration directory (`tests/integration/`, `integration/`, `src/test/integration/`).
2. If none, apply the `refactor-tests` mirroring convention to compute the expected test path and add it if it exists.
3. If still none, check the integration directory for a file with the same name and add it if it exists.
4. If still none, mark the file uncovered.

**Fallback:** if any changed file is uncovered, run the full suite as a safety net and report which files were uncovered. Otherwise run only the selected subset.

**Report before executing:** list the selected files, list the tests that will run, and note if the full suite was triggered by uncovered files.
