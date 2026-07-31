---
name: testing
description: Use when running tests, committing, or adding logging.
---

Always run the full test suite AND lint after code changes.

When committing, run `git status` first and stage ALL changes — modified files alongside renames and new files — before creating the commit.

Use real test IDs, real requirement IDs, and real implementations; wire dependencies through the app-level factory interface rather than concrete providers.

Logging should be file-only (no console output) unless explicitly requested otherwise.
