---
name: refactor-tests
description: Reorganize a flat test suite to mirror source packages and prune redundant/dead tests.
disable-model-invocation: true
argument-hint: "[project-path]"
---

You are refactoring a project's test layout to mirror its source package structure **and** simplifying the suite by removing redundant tests and consolidating parametrizable groups.

`PROJECT_PATH`: `$1` (default: `$PWD`)

End state:
- **Layout**: every test file at the location its language convention dictates for the source it exercises, imports rewritten to stay valid, full test suite passes with zero regressions.
- **Simplification**: redundant unit tests removed; clusters of tests that call the same function with varying inputs under the same assertion pattern consolidated into parametrized test cases.

Read `reference/patterns.md` (beside this SKILL.md) before doing any work — it holds path templates, language-detection heuristics, AST tool guidance, and ledger/plan schemas.

---

## Step 0 — Audio suppression

```sh
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_start || true
```

---

## Step 1 — Resolve project and detect stack

1. `PROJECT_PATH` defaults to `$PWD`. Resolve to absolute path; hard-stop if not a directory.
2. **Ledger resume.** If `$PROJECT_PATH/.scratch/refactor-tests/ledger.json` exists and `phase` is not `done`, print the recorded phase and resume from it. Otherwise initialize a fresh ledger with `phase: discovery`.
3. **Detect languages** by extension scan (respect `.gitignore`; skip `vendor/`, `node_modules/`, `.venv/`, `build/`, `.reference-projects/`, `.scratch/`).
4. **Detect runner(s)** per language via convention markers in `reference/patterns.md`.
5. Write detected languages, source roots, and runners into the ledger.

---

## Step 2 — Discovery: map source files to target test paths

For each source file in each detected source root:

1. Compute its **target test path** using the language path template from `reference/patterns.md`.
2. Find its **existing test file**: search by filename (`fd`/`rg`) using the flat-layout naming pattern (e.g. `test_<module>.py`). Also `rg` for imports of the module to catch tests that import it under a different name.
3. If the existing test path differs from the target path, record a move entry `{ from, to, language, source_file }`.
4. If no test file exists for this source file, skip — do not create empty test files.

**Cross-cutting classification:** a test file is cross-cutting when it cannot be cleanly attributed to a single source file. Use `search-codebase` to check whether the test exercises 2+ distinct non-mocked methods from different classes; if yes, classify as cross-cutting. Also treat as cross-cutting: conftest/fixture-only files, e2e tests, and tests whose import list spans packages with no dominant module. For each cross-cutting file: compute its target path in the language's integration directory (from `reference/patterns.md`), preserving the filename. Record in `plan.json` `cross_cutting` array as `{ from, to, language, reason }`. These are moved to the integration directory — not left in place.

**When a mapping is ambiguous** (test plausibly belongs to two modules), pick the one whose module name appears first in the test file's import list. Record the decision in the ledger `notes` field; do not stop to ask.

Write `$PROJECT_PATH/.scratch/refactor-tests/plan.json` with the full move list, rewrites, and unmapped entries.

---

## Step 3 — Baseline

Set ledger `phase: baseline`.

Run the full test suite using the detected runner command. Record into ledger `baseline`:
- pass count
- the full set of passing test ids
- the full set of failing test ids (pre-existing failures are baseline, not regressions)

---

## Phase A — Layout

### Step 4 — Move files

Set ledger `phase: moving`.

For each entry in `plan.json` moves:
1. Create any missing target directories (including `__init__.py` if the test tree uses package-style dirs — detect by presence of any `tests/**/__init__.py`).
2. `git mv <from> <to>` (falls back to `mv` outside git). Hard-stop on non-zero exit.
3. Record `{ from, to, cross_cutting: false }` in ledger `moves` immediately.

Then for each entry in `plan.json` `cross_cutting`:
1. Create the integration directory if absent (including `__init__.py` under the same rule as above).
2. `git mv <from> <to>` (falls back to `mv` outside git). Hard-stop on non-zero exit.
3. Record `{ from, to, cross_cutting: true }` in ledger `moves` immediately.

Build `id_map` in the ledger: for each moved file (regular and cross-cutting), record the old→new pytest/jest/go test id mapping (replace file path prefix in the id).

### Step 5 — Rewrite imports

Set ledger `phase: rewriting`.

For each moved file with a rewrite entry in `plan.json`:
- Use the language's AST parser/tool (per `reference/patterns.md` → Import rewriting). Never blind regex.
- For Python: use stdlib `ast` to locate relative imports whose depth changed, convert to absolute `from <pkg>.x import y`.
- For TS/JS: use `@babel/parser` or TypeScript compiler API to recompute `./`-relative specifiers.
- For Go: run `goimports` on the moved file.
- Files the parser cannot process: record as a **warning** in the ledger `warnings` field, leave imports unchanged, surface in the report.
- Record each completed rewrite in ledger `rewrites`.

### Step 6 — Validate layout

Set ledger `phase: validating`.

Re-run the full suite. Regression check: for each test id that passed in `baseline`, map it to its new id via `id_map` (or keep original id if unmoved), verify the mapped id still passes.

- **Healthy** (zero genuine regressions): record post-layout suite result in ledger `simplification.post_layout_baseline`. Print Phase A summary (see Final report). Advance to Phase B.
- **Regressed**: print the regressed test ids. **Do not roll back** — leave the tree for the user. Set `phase: done`. Emit `say_skill_done` and stop. Do not proceed to Phase B.

---

## Phase B — Simplification

Phase B runs immediately after a healthy Phase A. The baseline for Phase B is the post-layout suite result.

### Redundancy criteria

A test is a **simplification candidate** when it meets one of these criteria. **All criteria require identical fixture parameters, mock/stub configurations, and decorators between compared tests** unless the criterion says otherwise.

| Criterion | Action |
|-----------|--------|
| **Exact duplicate** | Remove one — byte/AST-identical body AND identical fixtures, mocks, decorators (ignoring only name and docstring) |
| **Dead test** | Remove — no `assert`/`expect`/`should`/`verify` statement in body |
| **Trivially true** | Remove — only `assert True`, `assertEqual(x, x)`, `expect(1).toBe(1)` |
| **Subset assertions** | Remove weaker — same function, same args, same fixtures+mocks; A's assertion list is a strict subset of B's |
| **Parametrize cluster** | Consolidate — N ≥ 3 tests call the same function with distinct args of the same structural type, identical fixtures+mocks, identical assertion pattern |
| **Parametrize pair** | Consolidate — N = 2 tests meeting cluster criteria where names differ only by trailing integer or single-letter suffix |

**Do NOT flag** as redundant: tests covering different scenarios, different input types, different fixture state, different mock return values, different decorators/markers, or any test the AST parser cannot fully analyze.

### Step 7 — Scan and build simplification plan

Set ledger `phase: simplifying`.

Parse every test file (post-layout) using the language's AST parser. For each test function extract: name, body AST, fixture parameters, mock/stub configurations, decorator list, primary source function called, call arguments, assertion list.

Apply criteria in order: exact duplicate → dead → trivially true → subset → parametrize cluster → parametrize pair.

For each **removal** candidate: emit `{ file, test_name, criterion, evidence }` (evidence = ≤2-line excerpt proving the criterion).

For each **parametrize** candidate:
- Verify expected assertion values share a structural type across all N tests (same type homogeneity). If they differ in type, classify as **unanalyzable**, skip.
- Emit `{ file, tests: [...], consolidated_name, consolidated_body, required_imports, criterion, evidence }` where `consolidated_body` is a concrete parametrized test body with the actual parameter tuples derived from the originals.

Ordering guard: if test A is a subset of B and B is itself a removal candidate, plan to remove B first.

Write `$PROJECT_PATH/.scratch/refactor-tests/simplification-plan.json`.

### Step 8 — Execute simplification

**Removals**: delete each named test function from its file using the language's AST editor — never blind text deletion. Record each in ledger `simplification.removals` after the write. If removing the last test function in a file, delete the file with `git rm`.

**Parametrizations** (atomic per entry): in a **single file write** — delete all N original test functions, insert the consolidated parametrized function, add any `required_imports` not already present. Record in ledger `simplification.parametrizations` in the same durable step. If the AST editor cannot perform the composite edit, record as `skipped` in the ledger with the error, leave the file unchanged, surface in the report.

### Step 9 — Validate simplification

Set ledger `phase: simplify-validating`.

Re-run the full suite. Regression check: compare against post-layout baseline. Exclude test ids in `simplification.removals` and replaced ids in `simplification.parametrizations` from the required-passing set. Verify each consolidated parametrized test id appears and passes.

- **Healthy**: set `phase: done`.
- **Regressed**: record regressed ids. **Do not roll back.** Set `phase: done` with regression flag.

---

## Final report

**Phase A — Layout:**
- Files moved: count and move list (sample if large)
- Imports rewritten: count with representative rewrites
- Cross-cutting (moved to integration dir): list with `from` → `to` and reason
- Baseline: `<N> passed, <M> failed`
- Post-layout: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions:` + ids

If Phase A regressed, print:
> **Phase B not reached** — resolve layout regressions first, then re-run to proceed to simplification.

**Phase B — Simplification:**
- Tests removed: count by criterion (exact-duplicate, dead, trivially-true, subset)
- Tests parametrized: count; before/after listing (original names → consolidated name + parameter tuples)
- Parametrizations skipped (AST editor failures): list with reasons
- Unanalyzable files (skipped by AST parser): list with reasons
- Post-simplification: `<N> passed, <M> failed` — `✓ zero regressions` or `✗ <k> regressions:` + ids

**Warnings**: AST parse/edit failures, imports not rewritten, runner-detection ambiguities

**Next steps** if regressed: files to inspect; `git checkout -- <paths>` to revert selectively

---

## Audio completion

```sh
proj="$(basename "${CLAUDE_PROJECT_DIR:-$PWD}")"
proj_say="$(printf '%s' "$proj" | tr '_-' '  ')"
msg="Refactor tests finished${proj_say:+ in ${proj_say}}."
[ -f ~/.claude/hooks/say-cue-lib.sh ] && . ~/.claude/hooks/say-cue-lib.sh && say_skill_done "$msg" || true
```

---

## Hard invariants

- Do NOT launch headless `claude` CLI processes via Bash.
- Never pass plan or file text as a shell argument — write to a temp file if Bash must read it.
- Bash non-zero exit = hard abort (emit `say_skill_cancel`, surface the error, stop).
- Import rewriting and test editing are AST-based per language — never blind regex search-replace.
- Each parametrize consolidation is a single atomic file write; ledger entry written in the same durable step.
- On a regressed health gate (either phase), **never** auto-rollback and never `git commit`.
- Update the ledger after every durable side effect so a mid-run compaction is recoverable.
- `rm -f` any temp file on every exit path, including hard-abort paths.
- Clear the audio-suppression marker via `say_skill_done`/`say_skill_cancel` on every exit path.
- **Do not commit.** Leave all changes in the working tree for the user to review and commit.
